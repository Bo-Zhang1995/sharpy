"""
PlotFlowField

Computes the flow velocity at a set of points (grid)

Args:

Returns:

Examples:

Notes:

"""
import os
import numpy as np
from tvtk.api import tvtk, write_data
from sharpy.utils.solver_interface import solver, BaseSolver
import sharpy.utils.generator_interface as gen_interface
import sharpy.utils.settings as settings
import sharpy.aero.utils.uvlmlib as uvlmlib
import ctypes as ct


@solver
class PlotFlowField(BaseSolver):
    solver_id = 'PlotFlowField'

    def __init__(self):
        self.settings_types = dict()
        self.settings_default = dict()

        self.settings_types['postproc_grid_generator'] = 'str'
        self.settings_default['postproc_grid_generator'] = 'box'

        self.settings_types['postproc_grid_input'] = 'dict'
        self.settings_default['postproc_grid_input'] = dict()

        self.settings_types['velocity_field_generator'] = 'str'
        self.settings_default['velocity_field_generator'] = 'SteadyVelocityField'

        self.settings_types['velocity_field_input'] = 'dict'
        self.settings_default['velocity_field_input'] = dict()

        self.settings_types['dt'] = 'float'
        self.settings_default['dt'] = 0.1

        self.settings_types['only_external'] = 'bool'
        self.settings_default['only_external'] = False

        self.settings_types['stride'] = 'int'
        self.settings_default['stride'] = 1

        self.settings = None
        self.data = None
        self.dir = 'output/'

    def initialise(self, data, custom_settings=None):
        self.data = data
        if custom_settings is None:
            self.settings = data.settings[self.solver_id]
        else:
            self.settings = custom_settings
        settings.to_custom_types(self.settings, self.settings_types, self.settings_default)

        self.dir =   self.data.case_route + 'output/' + self.data.case_name + '/' + 'GenerateFlowField/'
        if not os.path.isdir(self.dir):
            os.makedirs(self.dir)

        # init velocity generator
        velocity_generator_type = gen_interface.generator_from_string(
            self.settings['velocity_field_generator'])
        self.velocity_generator = velocity_generator_type()
        self.velocity_generator.initialise(self.settings['velocity_field_input'])

        # init postproc grid generator
        postproc_grid_generator_type = gen_interface.generator_from_string(
            self.settings['postproc_grid_generator'])
        self.postproc_grid_generator = postproc_grid_generator_type()
        self.postproc_grid_generator.initialise(self.settings['postproc_grid_input'])

    def output_velocity_field(self, ts):
        # Notice that SHARPy utilities deal with several two-dimensional surfaces
        # To be able to build 3D volumes, I will make use of the surface index as
        # the third index in space
        # It does not apply to the 'u' array because this way it is easier to
        # write it in paraview

        # Generate the grid
        vtk_info, grid = self.postproc_grid_generator.generate({'for_pos': self.data.structure.timestep_info[ts].for_pos[0:3]})

        # Compute the induced velocities
        nx = grid[0].shape[1]
        ny = grid[0].shape[2]
        nz = len(grid)

        u = np.zeros((nx,ny,nz,3), dtype=float)
        # u = np.zeros_like(grid, dtype=ct.c_double)
        if not self.settings['only_external']:
            for iz in range(nz):
                for ix in range(nx):
                    for iy in range(ny):
                        target_triad = grid[iz][:, ix, iy].astype(dtype=ct.c_double, order='F', copy=True)
                        u[ix, iy, iz, :] = uvlmlib.uvlm_calculate_total_induced_velocity_at_point(self.data.aero.timestep_info[ts],
                                                                                                  target_triad,
                                                                                                  self.data.structure.timestep_info[ts].for_pos[0:3])

        # Add the external velocities
        zeta = []
        u_ext = []
        for iz in range(nz):
            zeta.append(np.zeros((3,nx,ny), dtype=ct.c_double))
            u_ext.append(np.zeros((3,nx,ny), dtype=ct.c_double))
            for ix in range(nx):
                for iy in range(ny):
                    zeta[iz][:,ix,iy] = grid[iz][:, ix, iy]
                    u_ext[iz][:,ix,iy] = 0.0

        self.velocity_generator.generate({'zeta': zeta,
                                          'override': True,
                                          't': ts*self.settings['dt'].value,
                                          'ts': ts,
                                          'dt': self.settings['dt'].value,
                                          'for_pos': 0*self.data.structure.timestep_info[ts].for_pos},
                                         u_ext)

        # Add both velocities
        for iz in range(nz):
            for ix in range(nx):
                for iy in range(ny):
                    u[ix, iy, iz, :] += u_ext[iz][:,ix,iy]

        # Write the data
        vtk_info.point_data.add_array(u.reshape((-1, u.shape[-1]), order='F')) # Reshape the array except from the last dimension
        vtk_info.point_data.get_array(0).name = 'Velocity'
        vtk_info.point_data.update()

        filename = self.dir + "VelocityField_" + '%06u' % ts + ".vtk"
        write_data(vtk_info, filename)

    def run(self, online=False):
        if online:
            if divmod(self.data.ts, self.settings['stride'].value)[1] == 0:
                self.output_velocity_field(self.data.ts)
        else:
            for ts in range(0, len(self.data.aero.timestep_info) - 1):
                self.output_velocity_field(ts)
        return self.data


