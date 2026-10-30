# Purpose
# -------
# Configure the local MESA star-work build through its standard make rules.
#
# Inputs
# ------
# MESA_DIR supplies the installed MESA root. The existing nested compatibility
# check is retained for the intentionally-empty-directory convention.
#
# Outputs
# -------
# STAR selects the star build; actual targets, compiler settings, and recipes
# are supplied by the included MESA star/work_standard_makefile.

# Reject an unset installation root unless the existing compatibility check allows it
ifeq ($(MESA_DIR),)
ifeq ($($MESA_DIR_INTENTIONALLY_EMPTY),)
  $(error MESA_DIR environment variable is not set)
endif
endif

# Select the star executable family before loading the standard build rules
STAR = star

# Delegate all build targets and recipes to the configured MESA installation
include $(MESA_DIR)/star/work_standard_makefile
