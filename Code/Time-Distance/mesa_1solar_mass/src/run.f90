! Purpose
! -------
! Run the standard MESA stellar evolution job.
!
! Inputs
! ------
! Read job controls from the local inlist through run_star_support.
!
! Outputs
! -------
! Stop with code 1 if the job controls cannot be read; otherwise call do_run_star.

program run

   ! Import the standard job reader and stellar-evolution driver
   use run_star_support, only: do_read_star_job
   use run_star, only: do_run_star

   implicit none

   ! Store the read status and the fixed inlist filename
   integer :: ierr
   character(len=32) :: inlist_fname

   ierr = 0
   inlist_fname = 'inlist'

   ! Read job controls before running the stellar evolution driver
   call do_read_star_job(inlist_fname, ierr)
   if (ierr /= 0) stop 1

   ! Execute the configured model only after successful input parsing
   call do_run_star(inlist_fname)

end program run
