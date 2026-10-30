'''
Purpose
-------
Compute native positive-temporal-cross-spectrum spatial phase maps and optional
diagnostic magnetic contours.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for spatial_phase_analysis.py.

Notes
-----
Spatial cross-spectral phase, using the existing vorticity notebook definition.

The numerical map is arg(mean(F_lower * conj(F_higher))) over strictly positive
temporal FFT bins. The synthetic folded-phase example in agw_simulation.ipynb
is a different diagnostic and is deliberately not substituted here.
'''
# Import the libraries and shared helpers used by this module
from dataclasses import dataclass
from pathlib import Path
import copy

import contourpy
import numpy as np
from scipy.ndimage import gaussian_filter

import pipeline


DEFAULT_BAND_MHZ = (0.7, 3.1)
DEFAULT_CONTOUR_SIGMA_MM = 0.8
CONTOUR_COVERAGE_LEVEL = 0.15


class TemporalCrossSpectrum:
    '''
    Purpose
    -------
    Cache cumulative positive-frequency complex cross power for fast spatial phase-band
    edits.

    Inputs
    ------
    cubes: sequence of two np.ndarray
        Finite real lower/higher cubes with matching (t, y, x) shapes.
    dt_seconds: float
        Positive finite temporal cadence in seconds.
    phase_delay_seconds: float
        Finite lower-minus-higher observational sampling delay in seconds.

    Outputs
    -------
    spectrum: TemporalCrossSpectrum
        Cumulative complex spectrum and exact cyclic mHz coordinates, excluding DC and
        the even-length Nyquist bin.

    Notes
    -----
    Cache cumulative complex cross power; band edits need no new FFTs.
    '''
    def __init__(self, cubes, dt_seconds, *, phase_delay_seconds=0.):
        '''
        Purpose
        -------
        Build mean-subtracted temporal cross spectra and cumulative frequency sums.

        Inputs
        ------
        cubes: sequence of two np.ndarray
            Ordered lower/higher finite real cubes in (t, y, x) order.
        dt_seconds: float
            Positive temporal cadence in seconds.
        phase_delay_seconds: float
            Observational delay applied to the complex cross spectrum in seconds.

        Outputs
        -------
        None
            Stores exact positive mHz bins, spatial shape, complex prefix sums, and
            applied delay; incompatible/nonfinite cubes or invalid sampling raise
            ValueError.
        '''

        # Build mean-subtracted temporal cross spectra and cumulative frequency sums
        if len(cubes) != 2 or np.shape(cubes[0]) != np.shape(cubes[1]) or np.ndim(cubes[0]) != 3:
            raise ValueError('Spatial phase requires two matching [t,y,x] cubes.')
        if not np.isfinite(dt_seconds) or dt_seconds <= 0 or not np.isfinite(phase_delay_seconds):
            raise ValueError('Cadence must be positive and the phase delay finite.')
        nt = cubes[0].shape[0]
        count = (nt - 1)//2
        if count < 1:
            raise ValueError('At least three temporal samples are required.')
        self.frequency_mhz = np.fft.rfftfreq(nt, dt_seconds)[1:count+1]*1000.
        self.shape = cubes[0].shape[1:]
        transforms = []
        for cube in cubes:
            if not np.isrealobj(cube) or not np.isfinite(cube).all():
                raise ValueError('Spatial phase requires finite real Dopplergrams.')
            # Exactly the notebook's temporal mean subtraction. rFFT positive
            # bins equal FFT positive bins; DC and the even-N Nyquist bin vanish.
            centered = np.asarray(cube, dtype=float)-np.mean(cube, axis=0, keepdims=True)
            transforms.append(np.fft.rfft(centered, axis=0)[1:count+1])
        cross = transforms[0]*np.conjugate(transforms[1])
        if phase_delay_seconds:
            cross *= np.exp(2j*np.pi*self.frequency_mhz*1e-3*phase_delay_seconds)[:,None,None]
        del transforms
        self.prefix = np.empty((count+1, *self.shape), dtype=np.complex128)
        self.prefix[0] = 0.
        np.cumsum(cross, axis=0, out=self.prefix[1:])
        self.phase_delay_seconds = float(phase_delay_seconds)

    @property
    def full_band(self):
        '''
        Purpose
        -------
        Return the complete available strictly positive temporal FFT interval.

        Inputs
        ------
        None

        Outputs
        -------
        low, high: tuple of float
            First and final cached cyclic frequencies in mHz.
        '''

        # Return the complete available strictly positive temporal FFT interval
        return float(self.frequency_mhz[0]), float(self.frequency_mhz[-1])

    def band(self, bounds):
        '''
        Purpose
        -------
        Calculate a spatial phase map from the complex mean over selected positive FFT
        bins.

        Inputs
        ------
        bounds: sequence of two float
            Ordered inclusive frequency limits in mHz, allowing only floating-point
            boundary roundoff.

        Outputs
        -------
        phase, metadata: tuple
            (ny, nx) phase in degrees and requested/effective mHz bounds, bin count, and
            delay. Empty/out-of-range or reversed bands raise ValueError.
        '''

        # Calculate a spatial phase map from the complex mean over selected positive FFT
        # bins
        lo, hi = map(float, bounds)
        # JavaScript slider steps and NumPy FFT bins can differ by a few ulps.
        # Admit roundoff at a bin boundary, never a fraction of a physical bin.
        tolerance=16*np.finfo(float).eps*max(1.,abs(self.frequency_mhz[-1]))
        if not np.isfinite([lo, hi]).all() or lo > hi or lo < self.frequency_mhz[0]-tolerance or hi > self.frequency_mhz[-1]+tolerance:
            raise ValueError('Frequency bounds must be ordered and inside the positive FFT grid.')
        first = np.searchsorted(self.frequency_mhz, lo-tolerance, side='left')
        stop = np.searchsorted(self.frequency_mhz, hi+tolerance, side='right')
        if stop <= first:
            raise ValueError('The selected interval contains no temporal FFT bins.')
        average = (self.prefix[stop]-self.prefix[first])/(stop-first)
        return np.angle(average, deg=True), dict(requested_mhz=[lo,hi],
            effective_mhz=[float(self.frequency_mhz[first]),float(self.frequency_mhz[stop-1])],
            bin_count=int(stop-first), phase_delay_seconds=self.phase_delay_seconds)


def ordered_spectrum(cubes, config):
    '''
    Purpose
    -------
    Apply native physical height ordering and delay before constructing the temporal
    cross-spectrum cache.

    Inputs
    ------
    cubes: sequence of two np.ndarray
        Matching source Dopplergram cubes in (t, y, x) order.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    spectrum: TemporalCrossSpectrum
        Cached lower-times-conjugate-higher spatial cross spectrum.
    '''

    # Apply native physical height ordering and delay before constructing the temporal
    # cross-spectrum cache
    lower, higher, order = pipeline.TimeDistance(config).resolve_phase_analysis_cube_order(*cubes)
    delay = 0. if config['data']['source_type']=='single_cube' else float(order.get('phase_delay_seconds',0.))
    return TemporalCrossSpectrum((lower,higher),config['time_distance']['dt'],phase_delay_seconds=delay)


def magnetic_geometry(bx, by, bz):
    '''
    Purpose
    -------
    Compute horizontal field strength and polarity-independent inclination.

    Inputs
    ------
    bx: array-like
        Cartesian x field component in gauss.
    by: array-like
        Cartesian y field component in gauss.
    bz: array-like
        Upward z field component in gauss.

    Outputs
    -------
    horizontal, inclination: tuple of np.ndarray
        Horizontal strength in G and inclination folded to 0..90 degrees;
        zero/invalid-vector behavior follows the native orientation helper.

    Notes
    -----
    Field in gauss; fold the native +z inclination to polarity-free 0..90°.
    '''
    # Compute horizontal field strength and polarity-independent inclination
    bx,by,bz = np.broadcast_arrays(*[np.asarray(v,float) for v in (bx,by,bz)])
    orientation = pipeline.compute_magnetic_orientation_angles(bx,by,bz, magnitude_epsilon=0.)
    horizontal = np.hypot(bx,by)
    inclination = np.minimum(orientation['theta_deg'],180.-orientation['theta_deg'])
    return horizontal,inclination


def magnetic_selection(horizontal, inclination, threshold_G=10., threshold_deg=45.):
    '''
    Purpose
    -------
    Select finite magnetic pixels meeting horizontal-strength and inclination
    thresholds.

    Inputs
    ------
    horizontal: array-like
        Horizontal field-strength map in gauss.
    inclination: array-like
        Polarity-free inclination map in degrees.
    threshold_G: float
        Finite nonnegative minimum horizontal field strength in gauss.
    threshold_deg: float
        Finite minimum inclination from 0 to 90 degrees.

    Outputs
    -------
    mask: np.ndarray, bool
        Inclusive joint threshold selection; invalid threshold domains raise ValueError.
    '''

    # Select finite magnetic pixels meeting horizontal-strength and inclination
    # thresholds
    if not np.isfinite([threshold_G,threshold_deg]).all() or threshold_G<0 or not 0<=threshold_deg<=90:
        raise ValueError('Require a nonnegative field threshold and inclination within 0–90 degrees.')
    return (np.isfinite(horizontal)&np.isfinite(inclination)&
            (horizontal>=threshold_G)&(inclination>=threshold_deg))


def regional_magnetic_coverage(mask, x, y, sigma_mm):
    '''
    Purpose
    -------
    Form display-only Gaussian neighborhood coverage of a Boolean magnetic selection.

    Inputs
    ------
    mask: array-like
        Original Boolean selection with shape (len(y), len(x)).
    x: array-like
        Regular monotonic x coordinates in Mm.
    y: array-like
        Regular monotonic y coordinates in Mm.
    sigma_mm: float
        Nonnegative Gaussian spatial standard deviation in Mm; zero leaves the selection
        unsmoothed.

    Outputs
    -------
    coverage: np.ndarray
        Float mask or smoothed local coverage on the unchanged (y, x) grid; invalid
        sampling/shapes raise ValueError.

    Notes
    -----
    Display-only neighborhood coverage of the original Boolean selection.
    '''
    # Form display-only Gaussian neighborhood coverage of a Boolean magnetic selection
    if not np.isfinite(sigma_mm) or sigma_mm<0:
        raise ValueError('Contour smoothing must be finite and nonnegative in Mm.')
    x,y=_regular_axis(x),_regular_axis(y)
    if np.shape(mask)!=(len(y),len(x)):
        raise ValueError('Contour mask and spatial coordinates disagree.')
    values=np.asarray(mask,float)
    if sigma_mm==0:return values
    return gaussian_filter(values,sigma=(sigma_mm/abs(y[1]-y[0]),sigma_mm/abs(x[1]-x[0])),mode='nearest')


def contour_lines(mask, x, y, *, sigma_mm=0., coverage_level=CONTOUR_COVERAGE_LEVEL):
    '''
    Purpose
    -------
    Trace raw or smoothed magnetic-selection outlines in native physical spatial
    coordinates.

    Inputs
    ------
    mask: array-like
        Boolean magnetic selection on the native (y, x) grid.
    x: array-like
        Regular native x coordinates in Mm.
    y: array-like
        Regular native y coordinates in Mm.
    sigma_mm: float
        Display-only Gaussian coverage smoothing scale in Mm.
    coverage_level: float
        Contour level strictly between zero and one when smoothing is active; raw masks
        use 0.5.

    Outputs
    -------
    lines: dict
        xs/ys polyline arrays in Mm, clipped to the half-cell image boundary.

    Notes
    -----
    Trace raw selection or a smooth regional coverage outline in physical units.
    '''
    # Trace raw or smoothed magnetic-selection outlines in native physical spatial
    # coordinates
    x,y = np.asarray(x,float),np.asarray(y,float)
    if not np.isfinite(coverage_level) or not 0<coverage_level<1:
        raise ValueError('Contour coverage must be strictly between zero and one.')
    values=regional_magnetic_coverage(mask,x,y,sigma_mm)
    xx=np.r_[x[0]-(x[1]-x[0]),x,x[-1]+(x[-1]-x[-2])]
    yy=np.r_[y[0]-(y[1]-y[0]),y,y[-1]+(y[-1]-y[-2])]
    level=.5 if sigma_mm==0 else coverage_level
    lines=contourpy.contour_generator(x=xx,y=yy,z=np.pad(values,1)).lines(level)
    for line in lines:
        line[:,0]=np.clip(line[:,0],min(x)-abs(x[1]-x[0])/2,max(x)+abs(x[1]-x[0])/2)
        line[:,1]=np.clip(line[:,1],min(y)-abs(y[1]-y[0])/2,max(y)+abs(y[1]-y[0])/2)
    return dict(xs=[line[:,0] for line in lines],ys=[line[:,1] for line in lines])


def _regular_axis(axis):
    '''
    Purpose
    -------
    Validate a finite strictly monotonic regularly sampled spatial coordinate.

    Inputs
    ------
    axis: array-like
        Native x or y coordinate in consistent spatial units.

    Outputs
    -------
    axis: np.ndarray
        Floating-point native coordinate without resampling; invalid spacing/order
        raises ValueError.
    '''

    # Validate a finite strictly monotonic regularly sampled spatial coordinate
    axis=np.asarray(axis,float)
    if len(axis)<2 or not np.isfinite(axis).all() or not (np.all(np.diff(axis)>0) or np.all(np.diff(axis)<0)):
        raise ValueError('Spatial axes must be finite and strictly monotonic.')
    if not np.allclose(np.diff(axis),np.diff(axis)[0],rtol=1e-7,atol=1e-10):
        raise ValueError('The image renderer requires a regular native spatial grid; no resampling is applied.')
    return axis


def load_magnetic_snapshot(config, shape):
    '''
    Purpose
    -------
    Read registered vector fields from the first snapshot at the lower selected
    simulation height.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    shape: tuple of int
        Required native (ny, nx) grid shape.

    Outputs
    -------
    magnetic, metadata: tuple
        (horizontal G, folded inclination degrees) maps plus provenance, or None with
        explicit unavailable reasons. Spatial registration mismatches raise ValueError.

    Notes
    -----
    First snapshot at the lower selected height; only explicit vector fields.
    '''
    # Read registered vector fields from the first snapshot at the lower selected
    # simulation height
    data=config['data']
    if data['source_type']!='single_cube':
        return None,dict(status='unavailable',reason='Observed inputs provide LOS magnetograms, not registered Bx, By and Bz. Horizontal strength and inclination cannot be inferred from LOS alone.')
    path=Path(data['file'])
    F=pipeline.load_agw_filter_class(Path(config['_module_dir'])/'config.py')
    reader=F(config)
    with pipeline.nc.Dataset(path) as source:
        height_index=min((int(data['h1']),int(data['h2'])),key=lambda i:float(source['xc3'][i]))
        zero=(getattr(source,'ModelRefName','')=='Sun-v0' and '0 G flux density' in getattr(source,'Description',''))
        components=[]
        # Require explicit registered vector components and their declared magnetic
        # units
        for name in ('bb1','bb2','bb3'):
            if name not in source.variables:
                if zero:
                    components.append(np.zeros(shape));continue
                return None,dict(status='unavailable',reason=f'Missing vector component {name}; no magnetic geometry is invented.')
            variable=source[name]
            factor={'G':1.,'gauss':1.,'T':1e4}.get(getattr(variable,'units',''))
            if factor is None:
                return None,dict(status='unavailable',reason=f'{name} has absent or unsupported magnetic units.')
            # Select the first time sample and lower physical layer without resampling
            # the native map
            axes=reader.infer_netcdf_axis_order(variable)
            selection=[slice(None)]*4
            selection[axes['t']]=0;selection[axes['z']]=height_index
            remaining=[i for i in range(4) if i not in (axes['t'],axes['z'])]
            value=np.asarray(np.ma.filled(variable[tuple(selection)],np.nan),float)
            value=value.transpose(remaining.index(axes['y']),remaining.index(axes['x']))*factor
            if value.shape!=shape:
                raise ValueError('Vector magnetic map and Dopplergram grid are not registered.')
            components.append(value)
        horizontal,inclination=magnetic_geometry(*components)
        if not np.isfinite(horizontal).any():
            return None,dict(status='unavailable',reason='The vector snapshot contains no finite horizontal-field values.')
        return (horizontal,inclination),dict(status='available',source=str(path),components=['bb1','bb2','bb3'],
            units='G',frame_index=0,height_index=height_index,
            height_km=float(pipeline.infer_netcdf_height_pair_km(path,height_index,height_index)['h1_km']),
            convention='First snapshot at lower selected height; theta folded from +z to 0..90 degrees, independent of polarity. Diagnostic contours only; Dopplergrams unchanged.')


@dataclass
class SpatialInputs:
    '''
    Purpose
    -------
    Hold the raw spatial-phase reference, native coordinates, and optional magnetic
    diagnostics.

    Inputs
    ------
    reference: TemporalCrossSpectrum
        Original-cube temporal cross-spectrum cache before spatial/Gaussian filtering.
    x: np.ndarray
        Regular native x coordinates in Mm.
    y: np.ndarray
        Regular native y coordinates in Mm.
    magnetic: tuple or None
        Optional horizontal-strength G and folded-inclination degree maps.
    metadata: dict
        Dataset, source-version, coordinate, raw-reference, and magnetic provenance.

    Outputs
    -------
    inputs: SpatialInputs
        Loaded references used by the spatial explorer without changing the supplied
        Dopplergrams.
    '''

    reference: TemporalCrossSpectrum
    x: np.ndarray
    y: np.ndarray
    magnetic: tuple | None
    metadata: dict


def prepare_inputs(data):
    '''
    Purpose
    -------
    Prepare source-validated raw spatial diagnostics from an existing loaded dataset.

    Inputs
    ------
    data: ObservationData
        Loaded dataset with original/post-magnetogram cubes and analysis runtime; raw
        cubes are restored only when prior spatial masking requires them.

    Outputs
    -------
    inputs: SpatialInputs
        Original-cube cross spectrum, native Mm coordinates, optional vector-field maps,
        and provenance. Missing original data, registration errors, or changed sources
        raise ValueError.

    Notes
    -----
    Receive existing loaded data; restore raw cubes only after spatial masking.
    '''
    # Prepare source-validated raw spatial diagnostics from an existing loaded dataset
    if data.dopplergrams is None or data.analysis_config is None:
        raise ValueError('Original Dopplergram cubes and their analysis runtime are required; a phase-only diagram is insufficient.')
    config=copy.deepcopy(data.analysis_config)
    from dopplergram_recalculation import _version,input_reference
    reference=data.metadata.get('analysis_input') or input_reference(config,provenance='Current combined Bokeh analysis runtime')
    cfgdata=config['data']
    paths=(Path(cfgdata['file']),) if cfgdata['source_type']=='single_cube' else tuple(Path(cfgdata[k]) for k in ('v1','v2'))
    before=_version(paths)
    # Reject stale baseline sources before rebuilding raw spatial diagnostics
    recorded=config.get('_dopplergram_source_versions',[])
    if recorded:
        original_paths=[Path(entry[0]) for entry in recorded]
        if _version(original_paths)!=tuple(tuple(entry) for entry in recorded):
            raise ValueError('Original Dopplergram changed; reselect the dataset before spatial analysis.')
    filtering=reference.get('filtering',config['filtering'])
    masked=bool(data.metadata.get('processing_chain')) or (filtering.get('enabled') and
        filtering.get('magnetogram',{}).get('enabled') and 'magnetogram' in filtering.get('filter_sequence',[]))
    # Recover pre-mask cubes only when the existing preprocessing requires a raw spatial
    # reference
    raw=data.pre_gaussian_raw
    if raw is None:
        if masked:
            F=pipeline.load_agw_filter_class(Path(config['_module_dir'])/'config.py')
            raw=F(config).load_dopplergrams()
        else:
            raw=data.dopplergrams
    from magnetogram_workflow import DopplerDataset,_coordinates
    # Keep phase, vector-field diagnostics, and display axes on the same native spatial
    # grid
    coordinates,coordinate_meta=_coordinates(DopplerDataset(data.observation.id,data.observation.label,
        cfgdata['source_type'],paths,{}),config,raw[0].shape,paths)
    spectrum=ordered_spectrum(raw,config)
    magnetic,magnetic_meta=load_magnetic_snapshot(config,raw[0].shape[1:])
    if _version(paths)!=before:
        raise ValueError('Source changed during spatial analysis; reselect the dataset.')
    x,y=_regular_axis(coordinates['x_mm']),_regular_axis(coordinates['y_mm'])
    metadata=dict(dataset_id=data.observation.id,files=[str(p) for p in paths],
        analysis_input=reference,coordinates=coordinate_meta,magnetic=magnetic_meta,
        raw_reference='Original Dopplergrams before Magnetogram and Gaussian filtering',
        phase_method='temporal mean subtraction -> positive temporal FFT -> lower * conjugate(higher) -> complex band mean -> angle in degrees',
        notebook_source='Code/Time-Distance/vorticity.ipynb, cell 5; 0.7–3.1 mHz example',
        gaussian_source='Current combined Bokeh session; supplied checked reconstructed cubes',
        source_versions=before)
    return SpatialInputs(spectrum,x,y,magnetic,metadata)
