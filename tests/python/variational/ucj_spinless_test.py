# (C) Copyright IBM 2024.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Tests for spinless unitary cluster Jastrow ansatz."""

import itertools

import numpy as np
import pyscf
import pyscf.cc
import pytest

import ffsim


def test_n_params():
    for norb, n_reps, with_final_orbital_rotation in itertools.product(
        [1, 2, 3], [1, 2, 3], [False, True]
    ):
        operator = ffsim.random.random_ucj_op_spinless(
            norb, n_reps=n_reps, with_final_orbital_rotation=with_final_orbital_rotation
        )
        actual = ffsim.UCJOpSpinless.n_params(
            norb, n_reps, with_final_orbital_rotation=with_final_orbital_rotation
        )
        expected = len(operator.to_parameters())
        assert actual == expected

        interaction_pairs = list(
            itertools.combinations_with_replacement(range(norb), 2)
        )[:norb]

        actual = ffsim.UCJOpSpinless.n_params(
            norb,
            n_reps,
            interaction_pairs=interaction_pairs,
            with_final_orbital_rotation=with_final_orbital_rotation,
        )
        expected = len(operator.to_parameters(interaction_pairs=interaction_pairs))
        assert actual == expected

        with pytest.raises(ValueError, match="triangular"):
            actual = ffsim.UCJOpSpinless.n_params(
                norb,
                n_reps,
                interaction_pairs=[(1, 0)],
            )
        with pytest.raises(ValueError, match="Duplicate"):
            actual = ffsim.UCJOpSpinless.n_params(
                norb,
                n_reps,
                interaction_pairs=[(1, 0), (1, 0)],
            )


def test_parameters_roundtrip():
    rng = np.random.default_rng()
    norb = 5
    n_reps = 2

    for with_final_orbital_rotation in [False, True]:
        operator = ffsim.random.random_ucj_op_spinless(
            norb,
            n_reps=n_reps,
            with_final_orbital_rotation=with_final_orbital_rotation,
            seed=rng,
        )
        roundtripped = ffsim.UCJOpSpinless.from_parameters(
            operator.to_parameters(),
            norb=norb,
            n_reps=n_reps,
            with_final_orbital_rotation=with_final_orbital_rotation,
        )
        np.testing.assert_allclose(
            roundtripped.diag_coulomb_mats, operator.diag_coulomb_mats
        )
        np.testing.assert_allclose(
            roundtripped.orbital_rotations, operator.orbital_rotations
        )
        if with_final_orbital_rotation:
            np.testing.assert_allclose(
                roundtripped.final_orbital_rotation, operator.final_orbital_rotation
            )


def test_t_amplitudes_energy():
    mol = pyscf.gto.Mole()
    mol.build(
        atom=[["N", (0, 0, 0)], ["N", (0, 0, 1.0)]],
        basis="sto-6g",
        symmetry="Dooh",
    )
    n_frozen = 2
    active_space = range(n_frozen, mol.nao_nr())
    scf = pyscf.scf.RHF(mol).run()
    ccsd = pyscf.cc.CCSD(
        scf, frozen=[i for i in range(mol.nao_nr()) if i not in active_space]
    ).run()

    # Get molecular data and molecular Hamiltonian
    mol_data = ffsim.MolecularData.from_scf(scf, active_space=active_space)
    norb = mol_data.norb
    nelec = mol_data.nelec
    assert norb == 8
    assert nelec == (5, 5)
    mol_hamiltonian = mol_data.hamiltonian

    # Construct UCJ operator
    n_reps = 2
    operator = ffsim.UCJOpSpinless.from_t_amplitudes(ccsd.t2, t1=ccsd.t1, n_reps=n_reps)

    # Compute energy using entanglement forging
    reference_occupations_spatial = [
        (0, 1, 2),
        (0, 1, 3),
        (0, 1, 4),
        (1, 2, 3),
        (1, 2, 4),
        (2, 3, 4),
    ]
    reference_occupations = list(
        zip(reference_occupations_spatial, reference_occupations_spatial)
    )
    energy, _ = ffsim.multireference_state_prod(
        mol_hamiltonian,
        (operator, operator),
        reference_occupations,
        norb=norb,
        nelec=nelec,
    )
    energy_alt, _ = ffsim.multireference_state(
        mol_hamiltonian,
        operator,
        reference_occupations,
        norb=norb,
        nelec=nelec,
    )
    np.testing.assert_allclose(energy, energy_alt)
    np.testing.assert_allclose(energy, -108.519714)


def test_t_amplitudes_restrict_indices():
    # Build an H2 molecule
    mol = pyscf.gto.Mole()
    mol.build(
        atom=[["H", (0, 0, 0)], ["H", (0, 0, 1.8)]],
        basis="sto-6g",
        symmetry="Dooh",
    )
    scf = pyscf.scf.RHF(mol).run()
    ccsd = pyscf.cc.CCSD(scf).run()

    # Get molecular data and molecular Hamiltonian (one- and two-body tensors)
    mol_data = ffsim.MolecularData.from_scf(scf)
    norb = mol_data.norb

    # Construct UCJ operator
    n_reps = 2
    interaction_pairs = [(p, p + 1) for p in range(norb - 1)]

    operator = ffsim.UCJOpSpinless.from_t_amplitudes(
        ccsd.t2, n_reps=n_reps, interaction_pairs=interaction_pairs
    )
    other_operator = ffsim.UCJOpSpinless.from_parameters(
        operator.to_parameters(interaction_pairs=interaction_pairs),
        norb=norb,
        n_reps=n_reps,
        interaction_pairs=interaction_pairs,
    )

    assert ffsim.approx_eq(operator, other_operator, rtol=1e-12)
