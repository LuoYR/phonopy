# Copyright (C) 2011 Atsushi Togo
# All rights reserved.
#
# This file is part of phonopy.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in
#   the documentation and/or other materials provided with the
#   distribution.
#
# * Neither the name of the phonopy project nor the names of its
#   contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import numpy as np
import phonopy.structure.spglib as spg
from phonopy.structure.atoms import PhonopyAtoms as Atoms

def get_supercell(unitcell, supercell_matrix, symprec=1e-5):
    return Supercell(unitcell, supercell_matrix, symprec=symprec)

def get_primitive(supercell, primitive_frame, symprec=1e-5):
    return Primitive(supercell, primitive_frame, symprec=symprec)

def trim_cell(relative_axes, cell, symprec):
    """
    relative_axes: relative axes to supercell axes
    Trim positions outside relative axes

    """
    positions = cell.get_scaled_positions()
    numbers = cell.get_atomic_numbers()
    masses = cell.get_masses()
    magmoms = cell.get_magnetic_moments()
    lattice = cell.get_cell()
    trimed_lattice = np.dot(relative_axes.T, lattice)

    trimed_positions = []
    trimed_numbers = []
    if masses is None:
        trimed_masses = None
    else:
        trimed_masses = []
    if magmoms is None:
        trimed_magmoms = None
    else:
        trimed_magmoms = []
    extracted_atoms = []

    positions_in_new_lattice = np.dot(positions, np.linalg.inv(relative_axes).T)
    positions_in_new_lattice -= np.floor(positions_in_new_lattice)
    trimed_positions = np.zeros_like(positions_in_new_lattice)
    num_atom = 0

    mapping_table = np.arange(len(positions), dtype='intc')
    for i, pos in enumerate(positions_in_new_lattice):
        is_overlap = False
        if num_atom > 0:
            diff = trimed_positions[:num_atom] - pos
            diff -= np.rint(diff)
            # Older numpy doesn't support axis argument.
            # distances = np.linalg.norm(np.dot(diff, trimed_lattice), axis=1)
            # overlap_indices = np.where(distances < symprec)[0]
            distances = np.sqrt(
                np.sum(np.dot(diff, trimed_lattice) ** 2, axis=1))
            overlap_indices = np.where(distances < symprec)[0]
            if len(overlap_indices) > 0:
                assert len(overlap_indices) == 1
                is_overlap = True
                mapping_table[i] = extracted_atoms[overlap_indices[0]]

        if not is_overlap:
            trimed_positions[num_atom] = pos
            num_atom += 1
            trimed_numbers.append(numbers[i])
            if masses is not None:
                trimed_masses.append(masses[i])
            if magmoms is not None:
                trimed_magmoms.append(magmoms[i])
            extracted_atoms.append(i)

    trimed_cell = Atoms(numbers=trimed_numbers,
                        masses=trimed_masses,
                        magmoms=trimed_magmoms,
                        scaled_positions=trimed_positions[:num_atom],
                        cell=trimed_lattice,
                        pbc=True)

    return trimed_cell, extracted_atoms, mapping_table

def print_cell(cell, mapping=None, stars=None):
    symbols = cell.get_chemical_symbols()
    masses = cell.get_masses()
    magmoms = cell.get_magnetic_moments()
    lattice = cell.get_cell()
    print("Lattice vectors:")
    print("  a %20.15f %20.15f %20.15f" % tuple(lattice[0]))
    print("  b %20.15f %20.15f %20.15f" % tuple(lattice[1]))
    print("  c %20.15f %20.15f %20.15f" % tuple(lattice[2]))
    print("Atomic positions (fractional):")
    for i, v in enumerate(cell.get_scaled_positions()):
        num = " "
        if stars is not None:
            if i in stars:
                num = "*"
        num += "%d" % (i + 1)
        line = ("%5s %-2s%18.14f%18.14f%18.14f" %
                (num, symbols[i], v[0], v[1], v[2]))
        if masses is not None:
            line += " %7.3f" % masses[i]
        if magmoms is not None:
            line += "  %5.3f" % magmoms[i]
        if mapping is None:
            print(line)
        else:
            print(line + " > %d" % (mapping[i] + 1))

class Supercell(Atoms):
    """Build supercell from supercell matrix
    In this function, unit cell is considered
    [1,0,0]
    [0,1,0]
    [0,0,1].
    Supercell matrix is given by relative ratio, e.g,
    [-1, 1, 1]
    [ 1,-1, 1]  is for FCC from simple cubic.
    [ 1, 1,-1]
    In this case multiplicities of surrounding simple lattice are [2,2,2].

    First, create supercell with surrounding simple lattice.
    Second, trim the surrounding supercell with the target lattice.
    """

    def __init__(self, unitcell, supercell_matrix, symprec=1e-5):
        self._s2u_map = None
        self._u2s_map = None
        self._u2u_map = None
        self._supercell_matrix = np.array(supercell_matrix, dtype='intc')
        self._create_supercell(unitcell, symprec)

    def get_supercell_matrix(self):
        return self._supercell_matrix

    def get_supercell_to_unitcell_map(self):
        return self._s2u_map

    def get_unitcell_to_supercell_map(self):
        return self._u2s_map

    def get_unitcell_to_unitcell_map(self):
        return self._u2u_map

    def _create_supercell(self, unitcell, symprec):
        mat = self._supercell_matrix
        frame = self._get_surrounding_frame(mat)
        sur_cell, u2sur_map = self._get_simple_supercell(frame, unitcell)

        # Trim the simple supercell by the supercell matrix
        trim_frame = np.array([mat[0] / float(frame[0]),
                               mat[1] / float(frame[1]),
                               mat[2] / float(frame[2])])
        supercell, sur2s_map, mapping_table = trim_cell(trim_frame,
                                                        sur_cell,
                                                        symprec)

        num_satom = supercell.get_number_of_atoms()
        num_uatom = unitcell.get_number_of_atoms()
        multi = num_satom // num_uatom

        if multi != determinant(self._supercell_matrix):
            print("Supercell creation failed.")
            print("Probably some atoms are overwrapped. "
                  "The mapping table is give below.")
            print(mapping_table)
            Atoms.__init__(self)
        else:
            Atoms.__init__(self,
                           numbers=supercell.get_atomic_numbers(),
                           masses=supercell.get_masses(),
                           magmoms=supercell.get_magnetic_moments(),
                           scaled_positions=supercell.get_scaled_positions(),
                           cell=supercell.get_cell(),
                           pbc=True)
            self._u2s_map = np.arange(num_uatom) * multi
            self._u2u_map = dict([(j, i) for i, j in enumerate(self._u2s_map)])
            self._s2u_map = np.array(u2sur_map)[sur2s_map] * multi

    def _get_surrounding_frame(self, supercell_matrix):
        # Build a frame surrounding supercell lattice
        # For example,
        #  [2,0,0]
        #  [0,2,0] is the frame for FCC from simple cubic.
        #  [0,0,2]
        m = np.array(supercell_matrix)
        axes = np.array([[0, 0, 0],
                         m[:,0],
                         m[:,1],
                         m[:,2],
                         m[:,1] + m[:,2],
                         m[:,2] + m[:,0],
                         m[:,0] + m[:,1],
                         m[:,0] + m[:,1] + m[:,2]])
        frame = [max(axes[:,i]) - min(axes[:,i]) for i in (0,1,2)]
        return frame

    def _get_simple_supercell(self, multi, unitcell):
        # Scaled positions within the frame, i.e., create a supercell that
        # is made simply to multiply the input cell.
        positions = unitcell.get_scaled_positions()
        numbers = unitcell.get_atomic_numbers()
        masses = unitcell.get_masses()
        magmoms = unitcell.get_magnetic_moments()
        lattice = unitcell.get_cell()

        atom_map = []
        positions_multi = []
        numbers_multi = []
        if masses is None:
            masses_multi = None
        else:
            masses_multi = []
        if magmoms is None:
            magmoms_multi = None
        else:
            magmoms_multi = []
        for l, pos in enumerate(positions):
            for i in range(multi[2]):
                for j in range(multi[1]):
                    for k in range(multi[0]):
                        positions_multi.append([(pos[0] + k) / multi[0],
                                                (pos[1] + j) / multi[1],
                                                (pos[2] + i) / multi[2]])
                        numbers_multi.append(numbers[l])
                        if masses is not None:
                            masses_multi.append(masses[l])
                        atom_map.append(l)
                        if magmoms is not None:
                            magmoms_multi.append(magmoms[l])

        simple_supercell = Atoms(numbers=numbers_multi,
                                 masses=masses_multi,
                                 magmoms=magmoms_multi,
                                 scaled_positions=positions_multi,
                                 cell=np.dot(np.diag(multi), lattice),
                                 pbc=True)

        return simple_supercell, atom_map

class Primitive(Atoms):
    def __init__(self, supercell, primitive_matrix, symprec=1e-5):
        """
        primitive_matrix (3x3 matrix):
        Primitive lattice is given with respect to supercell by
           np.dot(primitive_matrix.T, supercell.get_cell())
        """
        self._primitive_matrix = np.array(primitive_matrix)
        self._symprec = symprec
        self._p2s_map = None
        self._s2p_map = None
        self._p2p_map = None
        self._smallest_vectors = None
        self._multiplicity = None

        self._primitive_cell(supercell)
        self._supercell_to_primitive_map(supercell.get_scaled_positions())
        self._primitive_to_primitive_map()
        self._set_smallest_vectors(supercell)

    def get_primitive_matrix(self):
        return self._primitive_matrix

    def get_primitive_to_supercell_map(self):
        return self._p2s_map

    def get_supercell_to_primitive_map(self):
        return self._s2p_map

    def get_primitive_to_primitive_map(self):
        return self._p2p_map

    def get_smallest_vectors(self):
        return self._smallest_vectors, self._multiplicity

    def _primitive_cell(self, supercell):
        trimed_cell, p2s_map, mapping_table = trim_cell(self._primitive_matrix,
                                                        supercell,
                                                        self._symprec)
        Atoms.__init__(self,
                       numbers=trimed_cell.get_atomic_numbers(),
                       masses=trimed_cell.get_masses(),
                       magmoms=trimed_cell.get_magnetic_moments(),
                       scaled_positions=trimed_cell.get_scaled_positions(),
                       cell=trimed_cell.get_cell(),
                       pbc=True)

        self._p2s_map = np.array(p2s_map, dtype='intc')

    def _supercell_to_primitive_map(self, pos):
        inv_F = np.linalg.inv(self._primitive_matrix)
        s2p_map = []
        for i in range(pos.shape[0]):
            s_pos = np.dot(pos[i], inv_F.T)
            for j in self._p2s_map:
                p_pos = np.dot(pos[j], inv_F.T)
                diff = p_pos - s_pos
                diff -= np.rint(diff)
                if (abs(diff) < self._symprec).all():
                    s2p_map.append(j)
                    break
        self._s2p_map = np.array(s2p_map, dtype='intc')

    def _primitive_to_primitive_map(self):
        """
        Mapping table from supercell index to primitive index
        in primitive cell
        """
        self._p2p_map = dict([(j, i) for i, j in enumerate(self._p2s_map)])

    def _set_smallest_vectors(self, supercell):
        self._smallest_vectors, self._multiplicity = _get_smallest_vectors(
            supercell, self, self._symprec)

#
# Get distance between a pair of atoms
#
def get_distance(cell, a0, a1, tolerance=1e-5):
    """
    Return the shortest distance between a pair of atoms in PBC
    """
    reduced_bases = get_reduced_bases(cell.get_cell(), tolerance)
    scaled_pos = np.dot(cell.get_positions(), np.linalg.inv(reduced_bases))
    # move scaled atomic positions into -0.5 < r <= 0.5
    for pos in scaled_pos:
        pos -= np.rint(pos)

    # Look for the shortest one in surrounded 3x3x3 cells
    distances = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k in (-1, 0, 1):
                distances.append(np.linalg.norm(
                        np.dot(scaled_pos[a0] - scaled_pos[a1] + [i, j, k],
                               reduced_bases)))
    return min(distances)

#
# Delaunay reduction
#
def get_reduced_bases(lattice,
                      method='delaunay',
                      tolerance=1e-5):
    """Apply reduction to basis vectors

    args:
        basis as row vectors, [a, b, c]^T
    return:
         reduced basin as row vectors, [a_red, b_red, c_red]^T
    """

    if method == 'niggli':
        return spg.niggli_reduce(lattice, eps=tolerance)
    else:
        return spg.delaunay_reduce(lattice, eps=tolerance)

def get_Delaunay_reduction(lattice, tolerance):
    """
    This is an implementation of Delaunay reduction.
    Some information is found in International table.
    This method is obsoleted and should not be used.

    lattice: row vectors
    return lattice: row vectors
    """

    extended_bases = np.zeros((4, 3), dtype='double')
    extended_bases[:3, :] = lattice
    extended_bases[3] = -np.sum(lattice, axis=0)

    for i in range(100):
        if _reduce_bases(extended_bases, tolerance):
            break
    if i == 99:
        print("Delaunary reduction was failed.")

    shortest = _get_shortest_bases_from_extented_bases(extended_bases,
                                                       tolerance)

    return shortest

def _reduce_bases(extended_bases, tolerance):
    metric = np.dot(extended_bases, extended_bases.T)
    for i in range(4):
        for j in range(i+1, 4):
            if metric[i][j] > tolerance:
                for k in range(4):
                    if (k != i) and (k != j):
                        extended_bases[k] += extended_bases[i]
                extended_bases[i] = -extended_bases[i]
                extended_bases[j] = extended_bases[j]
                return False

    # Reduction is completed.
    # All non diagonal elements of metric tensor is negative.
    return True

def _get_shortest_bases_from_extented_bases(extended_bases, tolerance):

    def mycmp(x, y):
        return cmp(np.vdot(x, x), np.vdot(y, y))

    basis = np.zeros((7, 3), dtype='double')
    basis[:4] = extended_bases
    basis[4]  = extended_bases[0] + extended_bases[1]
    basis[5]  = extended_bases[1] + extended_bases[2]
    basis[6]  = extended_bases[2] + extended_bases[0]
    # Sort bases by the lengthes (shorter is earlier)
    basis = sorted(basis, key=lambda vec: (vec ** 2).sum())

    # Choose shortest and linearly independent three bases
    # This algorithm may not be perfect.
    for i in range(7):
        for j in range(i + 1, 7):
            for k in range(j + 1, 7):
                if abs(np.linalg.det(
                        [basis[i], basis[j], basis[k]])) > tolerance:
                    return np.array([basis[i], basis[j], basis[k]])

    print("Delaunary reduction is failed.")
    return np.array(basis[:3], dtype='double')

#
# Shortest pairs of atoms in supercell (Wigner-Seitz like)
#
# This is currently no longer used in phonopy, but still used by
# phono3py. In phono3py, this is used to measure the shortest distance
# between arbitrary pair of atoms in supercell. Therefore this method
# may be moved to phono3py, but this way of use can also happen in
# phonopy in the future, so let's keep it for a while.
#
def get_equivalent_smallest_vectors(atom_number_supercell,
                                    atom_number_primitive,
                                    supercell,
                                    primitive_lattice,
                                    symprec):
    reduced_bases = get_reduced_bases(supercell.get_cell(), symprec)
    reduced_bases_inv = np.linalg.inv(reduced_bases)
    cart_positions = supercell.get_positions()

    # Atomic positions are confined into the delaunay-reduced superlattice.
    # Their positions will lie in the range -0.5 < x < 0.5, so that vectors
    # drawn between them have components in the range -1 < x < 1.
    def reduced_frac_pos(i):
        vec = np.dot(cart_positions[i], reduced_bases_inv)
        return vec - np.rint(vec)
    p_pos = reduced_frac_pos(atom_number_primitive)
    s_pos = reduced_frac_pos(atom_number_supercell)

    # The vector arrow is from the atom in the primitive cell to the
    # atom in the supercell.
    differences = _get_equivalent_smallest_vectors_simple(s_pos - p_pos,
                                                          reduced_bases,
                                                          symprec)

    # Return fractional coords in the basis of the primitive cell
    #  rather than the supercell.
    relative_scale = reduced_bases.dot(np.linalg.inv(primitive_lattice))
    return differences.dot(relative_scale)

# Given:
#  - A delaunay-reduced lattice (row vectors)
#  - A fractional vector (with respect to that lattice)
#      whose coords lie in the range (-1 < x < 1)
# Produce:
#  - All fractional vectors of shortest length that are translationally
#      equivalent to that vector under the lattice.
def _get_equivalent_smallest_vectors_simple(frac_vector,
                                            reduced_bases, # row vectors
                                            symprec):

    # Try all nearby images of the vector
    lattice_points = np.array([
        [i, j, k] for i in (-1, 0, 1)
                  for j in (-1, 0, 1)
                  for k in (-1, 0, 1)
    ])
    candidates = frac_vector + lattice_points

    # Filter out the best ones by computing cartesian lengths.
    # (A "clever" optimizer might try to skip the square root calculation here,
    #  but he would be wrong; we're comparing a *difference* to the tolerance)
    lengths = np.sqrt(np.sum(np.dot(candidates, reduced_bases)**2, axis=1))
    return candidates[lengths - lengths.min() < symprec]

def _get_smallest_vectors(supercell, primitive, symprec):
    """
    shortest_vectors:

      Shortest vectors from an atom in primitive cell to an atom in
      supercell in the fractional coordinates. If an atom in supercell
      is on the border centered at an atom in primitive and there are
      multiple vectors that have the same distance and different
      directions, several shortest vectors are stored. The
      multiplicity is stored in another array, "multiplicity".
      [atom_super, atom_primitive, multiple-vectors, 3]

    multiplicity:
      Number of multiple shortest vectors (third index of "shortest_vectors")
      [atom_super, atom_primitive]
    """

    # useful data from arguments
    p2s_map = primitive.get_primitive_to_supercell_map()
    size_super = supercell.get_number_of_atoms()
    size_prim = primitive.get_number_of_atoms()
    reduced_bases = get_reduced_bases(supercell.get_cell(), symprec)

    # Reduce all positions into the cell formed by the reduced bases.
    supercell_fracs = np.dot(supercell.get_positions(), np.linalg.inv(reduced_bases))
    supercell_fracs -= np.rint(supercell_fracs)
    primitive_fracs = supercell_fracs[list(p2s_map)]

    # For each vector, we will need to consider all nearby images in the reduced bases.
    lattice_points = np.array([
        [i, j, k] for i in (-1, 0, 1)
                  for j in (-1, 0, 1)
                  for k in (-1, 0, 1)
    ])

    # Here's where things get interesting.
    # We want to avoid manually iterating over all possible pairings of
    # supercell atoms and primitive atoms, because doing so creates a
    # tight loop in larger structures that is difficult to optimize.
    #
    # Furthermore, it seems wise to call numpy.dot on as large of an array
    # as possible, since numpy can shell out to BLAS to handle the
    # real heavy lifting.

    # For every atom in the supercell and every atom in the primitive cell,
    # we want 27 images of the vector between them.
    #
    # 'None' is used to insert trivial axes to make these arrays broadcast.
    #
    # shape: (size_super, size_prim, 27, 3)
    candidate_fracs = (
        supercell_fracs[:, None, None, :]    # shape: (size_super, 1, 1, 3)
        - primitive_fracs[None, :, None, :]  # shape: (1, size_prim, 1, 3)
        + lattice_points[None, None, :, :]   # shape: (1, 1, 27, 3)
    )

    # To compute the lengths, we want cartesian positions.
    #
    # Conveniently, calling 'numpy.dot' between a 4D array and a 2D array
    # does vector-matrix multiplication on each row vector in the last axis
    # of the 4D array.
    #
    # shape: (size_super, size_prim, 27, 3)
    candidate_carts = np.dot(candidate_fracs, reduced_bases)
    # shape: (size_super, size_prim, 27)
    lengths = np.sqrt(np.sum(candidate_carts**2, axis=-1))

    # Create the output, initially consisting of all candidate vectors scaled
    # by the primitive cell.
    #
    # shape: (size_super, size_prim, 27, 3)
    shortest_vectors = np.dot(candidate_fracs,
                              reduced_bases.dot(np.linalg.inv(primitive.get_cell())))

    # The last final bits are done in C.
    #
    # For each list of 27 vectors, we will identify the shortest ones
    # and move them to the front.
    shortest_vectors = np.array(shortest_vectors, dtype='double', order='C')
    multiplicity = np.zeros((size_super, size_prim), dtype='intc', order='C')

    import phonopy._phonopy as phonoc
    phonoc.gsv_move_smallest_vectors(shortest_vectors,
                                     multiplicity,
                                     lengths,
                                     symprec)

    return shortest_vectors, multiplicity

#
# Other tiny tools
#
def get_angles(lattice):
    a, b, c = get_cell_parameters(lattice)
    alpha = np.arccos(np.vdot(lattice[1], lattice[2]) / b / c) / np.pi * 180
    beta  = np.arccos(np.vdot(lattice[2], lattice[0]) / c / a) / np.pi * 180
    gamma = np.arccos(np.vdot(lattice[0], lattice[1]) / a / b) / np.pi * 180
    return alpha, beta, gamma

def get_cell_parameters(lattice):
    return np.sqrt(np.dot (lattice, lattice.transpose()).diagonal())

def get_cell_matrix(a, b, c, alpha, beta, gamma):
    # These follow 'matrix_lattice_init' in matrix.c of GDIS
    alpha *= np.pi / 180
    beta *= np.pi / 180
    gamma *= np.pi / 180
    a1 = a
    a2 = 0.0
    a3 = 0.0
    b1 = np.cos(gamma)
    b2 = np.sin(gamma)
    b3 = 0.0
    c1 = np.cos(beta)
    c2 = (2 * np.cos(alpha) + b1**2 + b2**2 - 2 * b1 * c1 - 1) / (2 * b2)
    c3 = np.sqrt(1 - c1**2 - c2**2)
    lattice = np.zeros((3, 3), dtype='double')
    lattice[0, 0] = a
    lattice[1] = np.array([b1, b2, b3]) * b
    lattice[2] = np.array([c1, c2, c3]) * c
    return lattice

def determinant(m):
    return (m[0][0] * m[1][1] * m[2][2] -
            m[0][0] * m[1][2] * m[2][1] +
            m[0][1] * m[1][2] * m[2][0] -
            m[0][1] * m[1][0] * m[2][2] +
            m[0][2] * m[1][0] * m[2][1] -
            m[0][2] * m[1][1] * m[2][0])
