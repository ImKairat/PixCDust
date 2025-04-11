#
# Copyright (C) 2024 Centre National d'Etudes Spatiales (CNES)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import os
from typing import Optional, Union, Tuple
import datetime

import geopandas as gpd

from eodag import EODataAccessGateway
from eodag import setup_logging

HELP_MESSAGE = """
Download products from hydroweb.next (https://hydroweb.next.theia-land.fr)
using EODAG (https://github.com/CS-SI/eodag)

Follow these steps:
1a. Generate an API-Key from hydroweb.next portal in your user settings
1b. Carefully store your API-Key
- either in your eodag configuration file (usually ~/.config/eodag/eodag.yml,
automatically generated the first time you use eodag) in
auth/credentials/apikey="PLEASE_CHANGE_ME"
- or in an environment variable 
`export EODAG__HYDROWEB_NEXT__AUTH__CREDENTIALS__APIKEY="PLEASE_CHANGE_ME"`
2. You can change download directory by modifying the variable path_out.
By default, current path is used.

For more information, please refer to EODAG Documentation 
https://eodag.readthedocs.io
"""


class Downloader:
    """Downloader class for hydroweb.next STAC API.

    Args:
        collection_name (str): name of the collection in hydroweb.next catalog
        geometry (str | [lonmin, latmin, lonmax, latmax] |
            gpd.GeoDataFrame | None, optional):
            a geometry used as search criteria. Defaults to None.
        dates ((datetime.date, datetime.date) | None, optional):
            minimum and maximum dates to be used as search criteria.
            Defaults to None.
        path_download (str, optional):
            download path. Defaults to "/tmp/hydroweb_next".
        verbose (int, optional): verbose level. Defaults to 0.

    Raises:
        AttributeError: if the geometry is not one
            of (str, tuple, list, gpd.GeoDataFrame)
    """

    PROVIDER = "hydroweb_next"

    def __init__(
        self,
        collection_name: str,
        geometry: Union[str, list, gpd.GeoDataFrame, None] = (None,),
        dates: Optional[Tuple[datetime.date, datetime.date]] | None = (None,),
        path_download: str = ("/tmp/hydroweb_next",),
        verbose: Optional[int] = (0,),
    ):
        self.collection_name = collection_name
        self.geometry = geometry
        self.dates = dates
        self.path_download = path_download
        self.verbose = verbose

        self.query_args = {}
        self.search_results = []
        self.dag = EODataAccessGateway()

        setup_logging(
            self.verbose
        )  # 0: nothing, 1: only progress bars, 2: INFO, 3: DEBUG

        # Set timeout to 30s
        os.environ["EODAG__HYDROWEB_NEXT__SEARCH__TIMEOUT"] = "30"

        if not os.path.isdir(self.path_download):
            os.mkdir(self.path_download)

        self.__check_collection_name()

        # Default search criteria when iterating over collection pages
        default_search_criteria = {
            "items_per_page": 2000,
            "provider": self.PROVIDER,
        }

        self.query_args = {
            "productType": self.collection_name,
        }

        if self.dates is not None:
            self.query_args["start"] = self.dates[0].strftime("%Y-%m-%dT%H:%M:%SZ")
            self.query_args["end"] = self.dates[1].strftime("%Y-%m-%dT%H:%M:%SZ")

        self.query_args.update(default_search_criteria)

    def _search(self, geom=None):
        if geom is not None:
            self.query_args["geom"] = geom

        # Iterate over all pages to find all products
        for page_results in self.dag.search_iter_page(**self.query_args):
            self.search_results.extend(page_results)

    @staticmethod
    def _explode_simplify_geometry(
        geometry: gpd.GeoDataFrame, tolerance: float | None = None
    ) -> gpd.GeoDataFrame:
        """this method explodes geodataframe containing multipolygons
        into single polygons. It allows to simplify the polygons in order to
        descrease their number of nodes. It also checks the number of nodes
        in the polygon in case it goes over a threshold

        Args:
            geometry (gpd.GeoDataFrame): a geodataframe containing search
                polygons of multipolygons
            tolerance (float | None, optional): a float number passed to the
                simplify method. Defaults to None.

        Raises:
            AttributeError: if the number of nodes in a single polygon
                is over 200

        Returns:
            gpd.GeoDataFrame: exploded geodataframe with simplified polygons
                if required
        """
        geom = geometry.explode(index_parts=True)

        if tolerance:
            geom["geometry"] = geom.geometry.simplify(
                tolerance=tolerance,
            )
        # verifying the number of nodes in each polygon
        geom["nodes_count"] = geom.apply(
            lambda row: len(row.geometry.exterior.coords),
            axis=1,
        )
        if (geom["nodes_count"] > 200).any():
            raise AttributeError(
                (
                    "One or several of your search polygons have too many nodes,"
                    "consider using the tolerance parameter"
                    "in order to simplify the polygons."
                )
            )

        return geom

    def __check_collection_name(self):
        list_collections = [
            d["ID"] for d in self.dag.list_product_types(provider=self.PROVIDER)
        ]

        if self.collection_name not in list_collections:
            raise ValueError(
                (
                    "Did not find collection_name in "
                    f"list of available collections in {self.PROVIDER}."
                    f"\nAvailable collections are: {list_collections}"
                )
            )

    def search_download(self, tolerance: float = None):
        if isinstance(self.geometry, str) or self.geometry is None:
            # TODO implement case to explode multipolyong in string
            self._search(self.geometry)
        elif isinstance(self.geometry, gpd.GeoDataFrame):
            geometries = self._explode_simplify_geometry(
                self.geometry,
                tolerance,
            )
            for geom in geometries.geometry.values:
                self._search(geom)

        else:
            raise AttributeError(
                (
                    "geometry should string or gpd.GeoDataFrame, "
                    f"received {type(self.geometry)} instead"
                )
            )

        # This command actually downloads the matching products
        downloaded_paths = self.dag.download_all(
            self.search_results, outputs_prefix=self.path_download
        )

        if downloaded_paths is None:
            print(
                f"No files downloaded! Verify API-KEY and/or \
product search configuration. \
{self.search_results}"
            )


class PixCDownloader(Downloader):
    def __init__(self, *args, **kwargs):
        super().__init__("SWOT_L2_HR_PIXC", *args, **kwargs)
