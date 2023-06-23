# (C) Copyright IBM 2023.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from pyscf.fci import cistring
from scipy.special import comb


def one_hot(shape: tuple[int, ...], index, *, dtype=float):
    """Return an array of all zeros except for a one at a specified index."""
    vec = np.zeros(shape, dtype=dtype)
    vec[index] = 1
    return vec


def slater_determinant(
    norb: int,
    occupied_orbitals: tuple[Sequence[int], Sequence[int]],
    dtype: type = complex,
) -> np.ndarray:
    """Return a Slater determinant."""
    alpha_orbitals, beta_orbitals = occupied_orbitals
    n_alpha = len(alpha_orbitals)
    n_beta = len(beta_orbitals)
    dim1 = comb(norb, n_alpha, exact=True)
    dim2 = comb(norb, n_beta, exact=True)
    alpha_bits = np.zeros(norb, dtype=bool)
    alpha_bits[list(alpha_orbitals)] = 1
    alpha_string = int("".join("1" if b else "0" for b in alpha_bits[::-1]), base=2)
    alpha_index = cistring.str2addr(norb, n_alpha, alpha_string)
    beta_bits = np.zeros(norb, dtype=bool)
    beta_bits[list(beta_orbitals)] = 1
    beta_string = int("".join("1" if b else "0" for b in beta_bits[::-1]), base=2)
    beta_index = cistring.str2addr(norb, n_beta, beta_string)
    return one_hot((dim1, dim2), (alpha_index, beta_index), dtype=dtype).reshape(-1)


def slater_determinant_one_rdm(
    norb: int,
    occupied_orbitals: tuple[Sequence[int], Sequence[int]],
    dtype: type = complex,
) -> np.ndarray:
    """Return the one-particle reduced density matrix of a Slater determinant.

    Args:
        norb: The number of spatial orbitals.
        occupied_orbitals: A tuple of two sequences of integers. The first
            sequence contains the indices of the occupied alpha orbitals, and
            the second sequence similarly for the beta orbitals.

    Returns:
        The one-particle reduced density matrix of the Slater determinant.
    """
    # TODO figure out why mypy complains about this line with
    # error: Need type annotation for "one_rdm"  [var-annotated]
    one_rdm = np.zeros((2 * norb, 2 * norb), dtype=dtype)  # type: ignore
    alpha_orbitals = np.array(occupied_orbitals[0])
    beta_orbitals = np.array(occupied_orbitals[1]) + norb
    one_rdm[(alpha_orbitals, alpha_orbitals)] = 1
    one_rdm[(beta_orbitals, beta_orbitals)] = 1
    return one_rdm