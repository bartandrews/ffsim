# (C) Copyright IBM 2023.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""The MolecularData class."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable

import numpy as np
import pyscf
import pyscf.cc
import pyscf.mcscf
import pyscf.mp
import pyscf.symm
from typing_extensions import deprecated

from ffsim.hamiltonians import MolecularHamiltonian


@dataclasses.dataclass
class MolecularData:
    """Class for storing molecular data.

    Attributes:
        atom: The coordinates of the atoms in the molecule.
        basis: The basis set, e.g. "sto-6g".
        spin: The spin of the molecule.
        symmetry: The symmetry of the molecule.
        norb: The number of spatial orbitals.
        nelec: The number of alpha and beta electrons.
        mo_coeff: Molecular orbital coefficients in the AO basis.
        mo_occ: Molecular orbital occupancies.
        active_space: The molecular orbitals included in the active space.
        core_energy: The core energy.
        one_body_tensor: The one-body tensor.
        two_body_integrals: The two-body integrals in compressed format.
        hf_energy: The Hartree-Fock energy.
        hf_mo_coeff: Hartree-Fock canonical orbital coefficients in the AO basis.
        hf_mo_occ: Hartree-Fock canonical orbital occupancies.
        mp2_energy: The MP2 energy.
        mp2_t2: The MP2 t2 amplitudes.
        ccsd_energy: The CCSD energy.
        ccsd_t1: The CCSD t1 amplitudes.
        ccsd_t2: The CCSD t2 amplitudes.
        fci_energy: The FCI energy.
        fci_vec: The FCI state vector.
        dipole_integrals: The dipole integrals.
        orbital_symmetries: The orbital symmetries.
    """

    # molecule information corresponding to attributes of pyscf.gto.Mole
    atom: list[tuple[str, tuple[float, float, float]]]
    basis: str
    spin: int
    symmetry: str | None
    # active space information
    norb: int
    nelec: tuple[int, int]
    mo_coeff: np.ndarray
    mo_occ: np.ndarray
    active_space: list[int]
    # molecular integrals
    core_energy: float
    one_body_integrals: np.ndarray
    two_body_integrals: np.ndarray
    # Hartree-Fock data
    hf_energy: float | None = None
    hf_mo_coeff: np.ndarray | None = None
    hf_mo_occ: np.ndarray | None = None
    # MP2 data
    mp2_energy: float | None = None
    mp2_t2: np.ndarray | None = None
    # CCSD data
    ccsd_energy: float | None = None
    ccsd_t1: np.ndarray | tuple[np.ndarray, np.ndarray] | None = None
    ccsd_t2: np.ndarray | tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
    # FCI data
    fci_energy: float | None = None
    fci_vec: np.ndarray | None = None
    # other information
    dipole_integrals: np.ndarray | None = None
    orbital_symmetries: list[str] | None = None

    @property
    def hamiltonian(self) -> MolecularHamiltonian:
        """The Hamiltonian defined by the molecular data."""
        return MolecularHamiltonian(
            one_body_tensor=self.one_body_integrals,
            two_body_tensor=pyscf.ao2mo.restore(1, self.two_body_integrals, self.norb),
            constant=self.core_energy,
        )

    @property
    def mole(self) -> pyscf.gto.Mole:
        """The PySCF Mole class for this molecular data."""
        mol = pyscf.gto.Mole()
        return mol.build(atom=self.atom, basis=self.basis, symmetry=self.symmetry)

    @staticmethod
    def from_scf(
        hartree_fock: pyscf.scf.SCF, active_space: Iterable[int] | None = None
    ) -> "MolecularData":
        """Initialize a MolecularData object from a Hartree-Fock calculation.

        Args:
            hartree_fock: The Hartree-Fock object.
            active_space: An optional list of orbitals to use for the active space.
        """
        if not hartree_fock.e_tot:
            hartree_fock = hartree_fock.run()
        hf_energy = hartree_fock.e_tot

        mol: pyscf.gto.Mole = hartree_fock.mol

        # Get core energy and one- and two-body integrals.
        if active_space is None:
            norb = mol.nao_nr()
            active_space = range(norb)
        active_space = list(active_space)
        norb = len(active_space)
        n_electrons = int(sum(hartree_fock.mo_occ[active_space]))
        n_alpha = (n_electrons + mol.spin) // 2
        n_beta = (n_electrons - mol.spin) // 2
        cas = pyscf.mcscf.CASCI(hartree_fock, norb, (n_alpha, n_beta))
        mo = cas.sort_mo(active_space, base=0)
        one_body_tensor, core_energy = cas.get_h1cas(mo)
        two_body_integrals = cas.get_h2cas(mo)

        # Get dipole integrals.
        charges = mol.atom_charges()
        coords = mol.atom_coords()
        nuc_charge_center = np.einsum("z,zx->x", charges, coords) / charges.sum()
        with mol.with_common_origin(nuc_charge_center):
            dipole_integrals = mol.intor("cint1e_r_sph", comp=3)
            mo_coeffs = hartree_fock.mo_coeff[:, active_space]
            dipole_integrals = np.einsum(
                "xij,ip,jq->xpq", dipole_integrals, mo_coeffs, mo_coeffs
            )

        # Get orbital symmetries.
        orbsym = None
        if mol.symmetry:
            orbsym = list(
                pyscf.symm.label_orb_symm(
                    mol,
                    mol.irrep_name,
                    mol.symm_orb,
                    hartree_fock.mo_coeff[:, active_space],
                )
            )

        return MolecularData(
            atom=mol.atom,
            basis=mol.basis,
            spin=mol.spin,
            symmetry=mol.symmetry or None,
            norb=norb,
            nelec=(n_alpha, n_beta),
            mo_coeff=hartree_fock.mo_coeff,
            mo_occ=hartree_fock.mo_occ,
            active_space=active_space,
            core_energy=core_energy,
            one_body_integrals=one_body_tensor,
            two_body_integrals=two_body_integrals,
            hf_energy=hf_energy,
            dipole_integrals=dipole_integrals,
            orbital_symmetries=orbsym,
        )

    @staticmethod
    @deprecated(
        "The from_mole method is deprecated. Instead, pass an SCF object directly to "
        "from_scf."
    )
    def from_mole(
        molecule: pyscf.gto.Mole,
        active_space: Iterable[int] | None = None,
        scf_func=pyscf.scf.RHF,
    ) -> "MolecularData":
        """Initialize a MolecularData object from a PySCF molecule.

        Args:
            molecule: The molecule.
            active_space: An optional list of orbitals to use for the active space.
            scf_func: The PySCF SCF function to use for the Hartree-Fock calculation.
        """
        hartree_fock = scf_func(molecule)
        hartree_fock.run()
        return MolecularData.from_scf(hartree_fock, active_space=active_space)

    def run_mp2(self, *, store_t2: bool = False):
        """Run MP2 and store results."""
        scf = pyscf.scf.RHF(self.mole)
        cas = pyscf.mcscf.CASCI(scf, ncas=self.norb, nelecas=self.nelec)
        mo = cas.sort_mo(self.active_space, mo_coeff=self.mo_coeff, base=0)
        frozen = [i for i in range(self.norb) if i not in self.active_space]
        mp2_solver = pyscf.mp.MP2(
            scf, frozen=frozen, mo_coeff=self.mo_coeff, mo_occ=self.mo_occ
        )
        _, mp2_t2 = mp2_solver.kernel(mo_coeff=mo)
        self.mp2_energy = mp2_solver.e_tot
        if store_t2:
            self.mp2_t2 = mp2_t2

    def run_fci(self, *, store_fci_vec: bool = False) -> None:
        """Run FCI and store results."""
        scf = pyscf.scf.RHF(self.mole)
        cas = pyscf.mcscf.CASCI(scf, ncas=self.norb, nelecas=self.nelec)
        mo = cas.sort_mo(self.active_space, mo_coeff=self.mo_coeff, base=0)
        _, _, fci_vec, _, _ = cas.kernel(mo_coeff=mo)
        self.fci_energy = cas.e_tot
        if store_fci_vec:
            self.fci_vec = fci_vec

    def run_ccsd(
        self,
        t1: np.ndarray | None = None,
        t2: np.ndarray | None = None,
        *,
        store_t1: bool = False,
        store_t2: bool = False,
    ) -> None:
        """Run CCSD and store results."""
        scf = pyscf.scf.RHF(self.mole)
        frozen = [i for i in range(self.norb) if i not in self.active_space]
        ccsd_solver = pyscf.cc.CCSD(
            scf, frozen=frozen, mo_coeff=self.mo_coeff, mo_occ=self.mo_occ
        )
        _, ccsd_t1, ccsd_t2 = ccsd_solver.kernel(t1=t1, t2=t2)
        self.ccsd_energy = ccsd_solver.e_tot
        if store_t1:
            self.ccsd_t1 = ccsd_t1
        if store_t2:
            self.ccsd_t2 = ccsd_t2
