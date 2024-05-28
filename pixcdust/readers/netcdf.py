"""This module reads SWOT Pixel Cloud Netcdfs"""

from dataclasses import dataclass, field
from datetime import datetime

import xarray as xr
import pandas as pd
import geopandas as gpd

from pixcdust.converters.geo_utils import geoxarray_to_geodataframe

@dataclass
class PixCNcSimpleConstants:
    """Class setting defaults values in SWOT pixel cloud files \
        such as name of attributes and variables
    """
    default_long_name: str = "longitude"
    default_lat_name: str = "latitude"
    default_cyc_num_name: str = 'cycle_number'
    default_pass_num_name: str = 'pass_number'
    default_tile_num_name: str = 'tile_number'
    default_time_start_name: str = 'time_granule_start'
    default_time_format_filename: str = "%Y%m%dT%H%M%S"
    default_time_format_attrs: str = '%Y-%m-%dT%H:%M:%S.%fZ'


@dataclass
class PixCNcSimpleReader:
    """Class for reading SWOT Pixel cloud official format files reader
    for most simple uses cases:
    It only reads in the pixel_cloud group

    Returns:
        _type_: _description_
    """

    path: list[str] | str
    variables: list[str] = None

    trusted_group: str = "pixel_cloud"
    forbidden_variables: list[str] = field(
        default_factory=lambda: [
            "pixc_line_qual",
            "pixc_line_to_tvp",
            "data_window_first_valid",
            "data_window_last_valid",
            "data_window_first_cross_track",
            "data_window_last_cross_track",
            "interferogram",
        ]
    )
    data: xr.Dataset = None

    @staticmethod
    def extract_info_from_nc_attrs(filename: str):
        """Extracts orbit information from global attributes\
            in SWOT pixel cloud netcdf

        Args:
            filename (str): path of SWOT PIXC Netcdf file

        Returns:
            str: time of granule start
            datetime.datetime: time of granule start
            int: cycle number
            int: pass number
            int: tile number
        """
        cst = PixCNcSimpleConstants()

        with xr.open_dataset(filename, engine='netcdf4') as ds_glob:
            tile_number = int(ds_glob.attrs[cst.default_tile_num_name])
            pass_number = int(ds_glob.attrs[cst.default_pass_num_name])
            cycle_number = int(ds_glob.attrs[cst.default_cyc_num_name])
            time_granule_start = ds_glob.attrs[cst.default_time_start_name]
            dt_time_start = datetime.strptime(
                time_granule_start,
                cst.default_time_format_attrs
            )

        return time_granule_start, dt_time_start, \
            cycle_number, pass_number, tile_number

    def open_dataset(self):
        """reads one pixc file and stores data in self.data
        """
        self.data = xr.open_dataset(
            self.path,
            group=self.trusted_group,
            engine="netcdf4",
        )
        if self.variables:
            self.data = self.data[self.variables]

    def open_mfdataset(self, orbit_info: bool = False):
        """ reads one or multiple pixc files and stores\
            a nested xarray in self.data.
        In this case, variables that are not one-dimensional
        along `points` dimension are not allowed and will be dropped:
            - 'pixc_line_qual',
            - 'pixc_line_to_tvp',
            - 'interferogram'
            - etc.


        Args:
            orbit_info (bool, optional): option to extract\
                the orbit information in data. Defaults to False.
        """

        if not orbit_info:
            self.data = xr.open_mfdataset(
                self.path,
                group=self.trusted_group,
                engine="netcdf4",
                drop_variables=self.forbidden_variables,
                combine="nested",
                concat_dim="points",
            )
        else:
            self.data = xr.open_mfdataset(
                self.path,
                group=self.trusted_group,
                engine="netcdf4",
                drop_variables=self.forbidden_variables,
                combine="nested",
                concat_dim="points",
                preprocess=self.__add_orbit_info,
            )

        if self.variables:
            # TODO: check if variables in forbidden variables before loading
            if orbit_info:
                self.variables.extend(
                    ['tile_num', 'cycle_num', 'pass_num', 'time']
                )
            self.data = self.data[self.variables]

    def __add_orbit_info(self, ds) -> xr.Dataset:
        """preprocessing function adding orbit information in pixc dataset

        Args:
            ds (xarray.Dataset): pixc dataset read by xarray.open_dataset

        Returns:
            xarray.Dataset: dataset augmented with orbit\
                information for each index
        """
        filename = ds.encoding['source']

        _, dt_time_start, cycle_number, pass_number, tile_number =\
            self.extract_info_from_nc_attrs(
                filename
            )

        ds['tile_num'] = tile_number
        ds['pass_num'] = pass_number
        ds['cycle_num'] = cycle_number
        ds['time'] = dt_time_start

        return ds

    def to_xarray(self) -> xr.Dataset:
        """returning an xarray.Dataset from object
        (this function exists for potential future compatibility)

        Returns:
            xr.Dataset: Dataset with information from file
        """

        return self.data

    def to_dataframe(self) -> pd.DataFrame:
        """returns a pandas.DataFrame from object

        Returns:
            pd.DataFrame: Dataframe with information from file
        """
        return self.data.to_dataframe()

    def to_geodataframe(
            self,
            **kwargs
            ) -> gpd.GeoDataFrame:
        """_summary_

        Args:
            crs (str | int, optional): Coordinate Reference System.\
                Defaults to 4326.
            area_of_interest (gpd.GeoDataFrame, optional): a geodataframe\
                containing polygons of interest where data will be restricted.\
                Defaults to None.

        Returns:
            gpd.GeoDataFrame: a geodataframe with information from file
        """

        cst = PixCNcSimpleConstants()

        return geoxarray_to_geodataframe(
            self.to_xarray(),
            long_name=cst.default_long_name,
            lat_name=cst.default_lat_name,
            **kwargs,
        )

