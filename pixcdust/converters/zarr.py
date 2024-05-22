import zcollection
import fsspec

from pixcdust.converters.core import PixCConverter
from pixcdust.readers.netcdf import PixCNcSimpleReader


class PixCNc2ZarrConverter(PixCConverter):
    """Class for converting Pixel Cloud files to Zarr database

    """

    def database_from_single_nc(self):
        """function to create a database from a single netcdf PIXC file
        (calls the corresponding multifile function, this function exist for future compatibility)
        """
        self.database_from_mf_nc()

    def database_from_mf_nc(self):
        """function to create a database from a multiple netcdf PIXC files
        """

        xr_ds = PixCNcSimpleReader(self.path_in, self.variables)

        xr_ds.open_mfdataset(orbit_info=True)

        # partition_handler = zcollection.partitioning.Date(('time', ), resolution='D')
        partition_handler = zcollection.partitioning.Sequence(("cycle_num", "pass_num", "tile_num" ))

        zc_ds = zcollection.Dataset.from_xarray(xr_ds.to_xarray())
        filesystem = fsspec.filesystem("file")
        collection = zcollection.create_collection(
            axis="time",
            ds=zc_ds,
            partition_handler=partition_handler,
            partition_base_dir=self.path_out,
            filesystem=filesystem
        )
        collection.insert(zc_ds)
