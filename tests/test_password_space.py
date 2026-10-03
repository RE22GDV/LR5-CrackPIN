import itertools
import string

import pytest

from crackpin.gpu import kernel_source,ordinal_word


@pytest.mark.parametrize("alphabet,width",[("01",4),(string.ascii_lowercase,2),(string.ascii_letters,1),(string.ascii_letters+string.digits,2)])
def test_ordinal_mapping_matches_cpu_generator(alphabet,width):
    for index,chars in enumerate(itertools.product(alphabet,repeat=width)):
        assert ordinal_word(index,alphabet,width)=="".join(chars)


@pytest.mark.parametrize("alphabet,width",[("a",5),("aa",5),("абв",5),("abc",0),("abc",9),("a!b",5)])
def test_kernel_rejects_unsupported_input(alphabet,width):
    with pytest.raises(ValueError): kernel_source(alphabet,width)


@pytest.mark.parametrize("index",[-1,100])
def test_index_bounds(index):
    with pytest.raises(ValueError): ordinal_word(index,"0123456789",2)
