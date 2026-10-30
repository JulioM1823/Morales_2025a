'''
Purpose
-------
Normalize simulation observable names and validate thermodynamic field units.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for simulation_observables.py.

Notes
-----
Explicit gas-pressure and plasma-beta contracts for CO5BOLD inputs.

These fields must be present in the source: internal energy is not pressure,
and a one-dimensional snapshot cannot substitute for a time-dependent cube.
'''

FIELD_NAMES = {
    'pressure': ('pressure', 'gas_pressure', 'pgas', 'p'),
    'plasma_beta': ('plasma_beta', 'beta'),
}
ALIASES = {name: canonical for canonical, names in FIELD_NAMES.items() for name in names}
PRESSURE_TO_CGS = {'dyn/cm^2': 1., 'dyn cm-2': 1., 'dyn cm^-2': 1.,
                   'dyne/cm^2': 1., 'erg/cm^3': 1., 'erg cm-3': 1.,
                   'Pa': 10., 'pascal': 10., 'barye': 1.}


def normalize(name):
    '''
    Purpose
    -------
    Translate supported observable aliases into their canonical names.

    Inputs
    ------
    name: str or None
        Observable name or alias; None is treated as an empty token.

    Outputs
    -------
    name: str
        Lowercase canonical observable token, or the normalized unmatched input.
    '''

    # Translate supported observable aliases into their canonical names
    token = str(name or '').strip().lower()
    return ALIASES.get(token, token)


def profile_units(field, units):
    '''
    Purpose
    -------
    Return the canonical thermodynamic unit and its numerical conversion factor.

    Inputs
    ------
    field: str
        Canonical thermodynamic field, pressure or plasma_beta.
    units: str
        Explicit stored unit convention to validate.

    Outputs
    -------
    unit, factor: tuple of str and float
        Pressure in dyn/cm^2 or dimensionless plasma beta; unsupported units raise
        ValueError.

    Notes
    -----
    Return output units and multiplier; reject unverified unit conventions.
    '''
    # Return the canonical thermodynamic unit and its numerical conversion factor
    if field == 'pressure' and units in PRESSURE_TO_CGS:
        return 'dyn/cm^2', PRESSURE_TO_CGS[units]
    if field == 'plasma_beta' and units in {'1', 'dimensionless'}:
        return '1', 1.
    raise ValueError(f'Unsupported or missing {field} units: {units!r}.')


def select_field(variables, field, *, ndim):
    '''
    Purpose
    -------
    Resolve a supported thermodynamic field only among variables of the required
    dimensionality.

    Inputs
    ------
    variables: mapping
        Stored variable names and array-like variables exposing ndim and units.
    field: str
        Canonical thermodynamic field to locate.
    ndim: int
        Required number of array dimensions.

    Outputs
    -------
    name, variable: tuple
        Matched stored name and variable after validating its units; unavailable fields
        raise ValueError.

    Notes
    -----
    Resolve aliases only among full fields of the requested dimensionality.
    '''
    # Resolve a supported thermodynamic field only among variables of the required
    # dimensionality
    lookup = {name.lower(): (name, value) for name, value in variables.items()
              if value.ndim == ndim}
    for candidate in FIELD_NAMES[field]:
        if candidate in lookup:
            name, variable = lookup[candidate]
            profile_units(field, getattr(variable, 'units', ''))
            return name, variable
    raise ValueError(f'{field} requires a stored {ndim}D field; available fields: '
                     + ', '.join(sorted(lookup)))


def spatial_plot_units(config):
    '''
    Purpose
    -------
    Resolve the conversion and label for thermodynamic simulation maps.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    conversion: tuple or None
        Multiplicative factor and plot label for pressure/beta, or None for other source
        types or observables.

    Notes
    -----
    Thermodynamic map conversion/label; None preserves existing velocity plots.
    '''
    # Resolve the conversion and label for thermodynamic simulation maps
    data = config.get('data', {})
    if data.get('source_type') != 'single_cube':
        return None
    field = normalize(data.get('observable', ''))
    if field not in FIELD_NAMES:
        return None
    _, factor = profile_units(field, data.get('observable_units', ''))
    label = r'$P_{gas}$ [dyn cm$^{-2}$]' if field == 'pressure' else r'Plasma $\beta$ [dimensionless]'
    return factor, label
