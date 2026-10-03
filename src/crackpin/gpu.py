"""Python-керування OpenCL-перебором коротких ASCII-паролів.

MD5 одного блока за RFC 1321. Алфавіт і довжина спеціалізуються при компіляції.
Імпорти PyOpenCL/Numpy ліниві: звичайна бібліотека й CI не залежать від GPU.
"""

from __future__ import annotations

import hashlib
import math
from time import perf_counter


def ordinal_word(index: int, alphabet: str, width: int) -> str:
    if type(index) is not int or not 0<=index<len(alphabet)**width:
        raise ValueError("Індекс поза простором")
    result=[alphabet[0]]*width
    for pos in range(width-1,-1,-1):
        index,remainder=divmod(index,len(alphabet))
        result[pos]=alphabet[remainder]
    return "".join(result)


def kernel_source(alphabet: str, width: int) -> str:
    if type(width) is not int or not 1<=width<=8:
        raise ValueError("GPU-стенд підтримує 1–8 символів")
    if not isinstance(alphabet,str) or len(alphabet)<2 or len(set(alphabet))!=len(alphabet) or not all(c.isascii() and c.isalnum() for c in alphabet):
        raise ValueError("Потрібен алфавіт з унікальних ASCII-літер і цифр")
    shifts=[7,12,17,22]*4+[5,9,14,20]*4+[4,11,16,23]*4+[6,10,15,21]*4
    rounds=[]
    for i in range(64):
        constant=int(abs(math.sin(i+1))*2**32)&0xffffffff
        if i<16: function="((b & c) | (~b & d))"; g=i
        elif i<32: function="((d & b) | (~d & c))"; g=(5*i+1)%16
        elif i<48: function="(b ^ c ^ d)"; g=(3*i+5)%16
        else: function="(c ^ (b | ~d))"; g=(7*i)%16
        rounds.append(f"{{ uint f={function}; uint old_d=d; d=c; c=b; b=b+rotate(a+f+0x{constant:08x}u+x[{g}], (uint){shifts[i]}); a=old_d; }}")
    return f'''
    __constant char alphabet[]="{alphabet}";
    inline void hash_ordinal(ulong ordinal, __private uint *digest) {{
        uint x[16];
        #pragma unroll
        for (int i=0;i<16;i++) x[i]=0u;
        #pragma unroll
        for (int pos={width-1};pos>=0;pos--) {{
            uint ch=(uint)(uchar)alphabet[ordinal % (ulong){len(alphabet)}];
            ordinal /= (ulong){len(alphabet)};
            x[pos>>2] |= ch << ((pos & 3)*8);
        }}
        x[{width>>2}] |= 0x80u << {(width&3)*8};
        x[14]={width*8}u;
        uint a=0x67452301u,b=0xefcdab89u,c=0x98badcfeu,d=0x10325476u;
        {''.join(rounds)}
        digest[0]=a+0x67452301u; digest[1]=b+0xefcdab89u;
        digest[2]=c+0x98badcfeu; digest[3]=d+0x10325476u;
    }}
    __kernel void hashes(__global const ulong *indices, __global uint *output) {{
        size_t i=get_global_id(0); uint h[4]; hash_ordinal(indices[i],h);
        for (int j=0;j<4;j++) output[4*i+j]=h[j];
    }}
    __kernel void search(ulong base, ulong limit, __global const uint *target,
        __global uint *found, __global ulong *result) {{
        ulong ordinal=base+(ulong)get_global_id(0);
        if (ordinal>=limit) return;
        uint h[4]; hash_ordinal(ordinal,h);
        if (h[0]==target[0] && h[1]==target[1] && h[2]==target[2] && h[3]==target[3]) {{
            if (atomic_cmpxchg((volatile __global unsigned int *)found,0u,1u)==0u)
                result[0]=ordinal;
        }}
    }}
    '''


class GPUEngine:
    def __init__(self):
        import numpy as np
        import pyopencl as cl
        self.np=np
        self.cl=cl
        devices=[d for p in cl.get_platforms() for d in p.get_devices(device_type=cl.device_type.GPU)]
        if not devices: raise RuntimeError("OpenCL GPU не знайдено")
        self.device=max(devices,key=lambda d:d.max_compute_units)
        self.context=cl.Context([self.device])
        self.queue=cl.CommandQueue(self.context,properties=cl.command_queue_properties.PROFILING_ENABLE)
        self.programs={}
        self.compilation_seconds={}

    def metadata(self):
        d=self.device
        return {"name":d.name.strip(),"vendor":d.vendor,"driver_version":d.driver_version,
            "opencl_version":d.version,"opencl_c_version":d.opencl_c_version,
            "compute_units":d.max_compute_units,"global_memory_bytes":d.global_mem_size,
            "max_work_group_size":d.max_work_group_size,"pyopencl_version":self.cl.VERSION_TEXT}

    def program(self, alphabet, width):
        key=(alphabet,width)
        if key not in self.programs:
            started=perf_counter()
            program=self.cl.Program(self.context,kernel_source(alphabet,width)).build()
            self.programs[key]={"hashes":self.cl.Kernel(program,"hashes"),"search":self.cl.Kernel(program,"search")}
            self.compilation_seconds[key]=perf_counter()-started
        return self.programs[key]

    def hashes(self, alphabet, width, indices):
        cl,np=self.cl,self.np
        program=self.program(alphabet,width)
        values=np.asarray(indices,dtype=np.uint64)
        output=np.empty((len(values),4),dtype=np.uint32)
        source=cl.Buffer(self.context,cl.mem_flags.READ_ONLY|cl.mem_flags.COPY_HOST_PTR,hostbuf=values)
        result=cl.Buffer(self.context,cl.mem_flags.WRITE_ONLY,output.nbytes)
        event=program["hashes"](self.queue,(len(values),),None,source,result)
        event.wait()
        cl.enqueue_copy(self.queue,output,result).wait()
        return [r.tobytes().hex() for r in output]

    def scan(self, alphabet, width, *, batch_size=2**25, deadline=float("inf")):
        cl,np=self.cl,self.np
        program=self.program(alphabet,width)
        expected=alphabet[-1]*width
        target=np.frombuffer(hashlib.md5(expected.encode("ascii")).digest(),dtype=np.uint32).copy()
        flag=np.zeros(1,dtype=np.uint32)
        result=np.zeros(1,dtype=np.uint64)
        flags=cl.mem_flags
        count=len(alphabet)**width
        begun=perf_counter()
        target_buffer=cl.Buffer(self.context,flags.READ_ONLY|flags.COPY_HOST_PTR,hostbuf=target)
        flag_buffer=cl.Buffer(self.context,flags.READ_WRITE|flags.COPY_HOST_PTR,hostbuf=flag)
        result_buffer=cl.Buffer(self.context,flags.READ_WRITE|flags.COPY_HOST_PTR,hostbuf=result)
        attempts=0
        kernel_seconds=0
        batch_times=[]
        while attempts<count and perf_counter()<deadline:
            size=min(batch_size,count-attempts)
            padded=((size+255)//256)*256
            event=program["search"](self.queue,(padded,),(256,),np.uint64(attempts),np.uint64(attempts+size),target_buffer,flag_buffer,result_buffer)
            event.wait()
            elapsed=(event.profile.end-event.profile.start)/1e9
            batch_times.append(elapsed)
            kernel_seconds+=elapsed
            attempts+=size
        cl.enqueue_copy(self.queue,flag,flag_buffer).wait()
        cl.enqueue_copy(self.queue,result,result_buffer).wait()
        wall_seconds=perf_counter()-begun
        recovered=ordinal_word(int(result[0]),alphabet,width) if flag[0] else None
        if recovered is not None and hashlib.md5(recovered.encode("ascii")).digest()!=target.tobytes():
            raise AssertionError("GPU повернув неправильний прообраз")
        return {"space":count,"attempts":attempts,"expected":expected,"recovered":recovered,
            "target_md5":target.tobytes().hex(),"complete":attempts==count and recovered==expected,
            "wall_seconds":wall_seconds,"kernel_seconds":kernel_seconds,"batch_size":batch_size,
            "batch_count":len(batch_times),"kernel_batch_seconds":batch_times,
            "rate_wall_per_second":attempts/wall_seconds,"rate_kernel_per_second":attempts/kernel_seconds if kernel_seconds else 0,
            "program_build_seconds":self.compilation_seconds[(alphabet,width)]}
