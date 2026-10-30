! Purpose
! -------
! Expose standard MESA run-star extra hooks without custom overrides.
!
! Inputs
! ------
! MESA star, constants, and mathematics modules plus standard_run_star_extras.inc.
!
! Outputs
! -------
! Compile the standard extra-hook implementation into run_star_extras.

! ***********************************************************************
!
!   Copyright (C) 2010-2025  Bill Paxton & The MESA Team
!
!   This program is free software: you can redistribute it and/or modify
!   it under the terms of the GNU Lesser General Public License
!   as published by the Free Software Foundation,
!   either version 3 of the License, or (at your option) any later version.
!
!   This program is distributed in the hope that it will be useful,
!   but WITHOUT ANY WARRANTY; without even the implied warranty of
!   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
!   See the GNU Lesser General Public License for more details.
!
!   You should have received a copy of the GNU Lesser General Public License
!   along with this program. If not, see <https://www.gnu.org/licenses/>.
!
! ***********************************************************************

module run_star_extras

   ! Import the state, library, and constants required by the standard hook include
   use star_lib
   use star_def
   use const_def
   use math_lib

   implicit none

   ! these routines are called by the standard run_star check_model
contains

   ! Keep the shipped standard callbacks as this work directory hook implementation
   include 'standard_run_star_extras.inc'

end module run_star_extras
