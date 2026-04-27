from pystac_client import Client
import rasterio
import planetary_computer
import numpy as np

from rasterio import windows, features, warp
from rasterio.features import shapes
from rasterio.enums import Resampling

from shapely.geometry import shape, Polygon

import geopandas as gpd

import cv2

import torch
import torch.nn as nn

from PIL import Image


#SPECIFICALLY FOR SENTINEL ITEMS
#Primary class that performs actions on a a particular planetary_computer item
class Sentinel_Item:
    def __init__(self, item, aoi):
        self.item = item
        
        #Collect the specific window in the item
        with rasterio.open(item.assets["visual"].href) as ds:
            aoi_bounds = features.bounds(aoi)
            warped_aoi_bounds = warp.transform_bounds("epsg:4326", ds.crs, *aoi_bounds)
            aoi_window = windows.from_bounds(*warped_aoi_bounds, transform=ds.transform)
            self.window = aoi_window.round_offsets().round_lengths()
            self.transform = ds.window_transform(self.window)
            self.crs = ds.crs



    #Function to display the visual of the item
    def get_visual(self):
        #Setup the image
        with rasterio.open(self.item.assets["visual"].href) as ds:
            band_data = ds.read(window=self.window)

        #Format the image for viewing
        img = Image.fromarray(np.transpose(band_data, axes=[1, 2, 0]))

        return img
    

    def get_array(self):
        with rasterio.open(self.item.assets["visual"].href) as ds:
            return ds.read(window=self.window)



    #A function to collect the data from a specific band, not just visual
    def collect_band_data(self, band, shape = None):
        href = self.item.assets[band].href

        with rasterio.open(href) as ds:            
            #Method of reading the data depends on whether we neeed to define the exact shape
            if shape == None:
                return ds.read(1, window=self.window)    
            else:
                return ds.read(
                    1,
                    window = self.window,
                    out_shape = shape,
                    resampling = Resampling.bilinear
                )



    #Function to collect the thermal data for a given item
    #Thermal logic taken from: https://www.sciencedirect.com/science/article/pii/S0924271621001337?via%3Dihub
    def get_thermals(self):
        self.thermal_bands = {}

        self.thermal_bands['B8A'] = self.collect_band_data('B8A')

        ref_shape = self.thermal_bands['B8A'].shape
        for band in ['B11', 'B12']:
            self.thermal_bands[band] = self.collect_band_data(band, shape = ref_shape)

        SWIR1, SWIR2, NIR = self.thermal_bands['B11'], self.thermal_bands['B12'], self.thermal_bands['B8A']

        self.thermal_array1 = (SWIR2 - SWIR1)/NIR
        self.thermal_array2 = (SWIR2 - SWIR1)/(SWIR1 - NIR)

        viewable_array1 = np.clip(self.thermal_array1/20 , 0, 1)
        viewable_array2 = np.clip(self.thermal_array2/20 , 0, 1)

        thermal_view1 = Image.fromarray((viewable_array1 * 255).astype("uint8"))
        thermal_view2 = Image.fromarray((viewable_array2 * 255).astype("uint8"))

        return [thermal_view1, thermal_view2]



    #Method to collect the buildings in the scene
    #Requires input model
    #Returns Mask and Polygons as gpd
    def get_buildings(self, model):
        img = self.get_array()
        

        #-----------------------INFERENCE THE IMAGE--------------------------#
        tile_size = 256
        C, H, W = img.shape

        #Break the image into tiles
        tiles = []
        coords = []
        shape_list = []
        for y in range(0, H, tile_size):
            for x in range(0, W, tile_size):
                tile = img[:, y:y+tile_size, x:x+tile_size]

                c, h, w = tile.shape

                # store original shape
                shape_list.append((h, w))


                padded = np.zeros((c, tile_size, tile_size), dtype=tile.dtype)
                padded[:, :h, :w] = tile

                tiles.append(padded)
                coords.append((y, x))



        #Inference each individual tile
        pred_tiles = []
        for tile in tiles:
            img = torch.tensor(tile / 255.0, dtype=torch.float32).unsqueeze(0)

            with torch.no_grad():
                output = model(img)

            pred = (output.squeeze().numpy() > 0.5).astype(np.uint8)
            pred_tiles.append(pred)



        #-----------------------CREATE THE MASK--------------------------#
        #Stitch the output tiles back together into one mask
        #This step removes the padding placed before inference
        full_mask = np.zeros((H, W), dtype=np.uint8)

        for (y, x), pred, (h, w) in zip(coords, pred_tiles, shape_list):
            full_mask[y:y+h, x:x+w] = pred[:h, :w]

        #Cleam up the mask (fill holes and eliminate noise)
        full_mask = full_mask.astype(np.uint8)

        # remove small noise
        kernel = np.ones((2,2), np.uint8)
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_OPEN, kernel)

        # fill small holes
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_CLOSE, kernel)




        #-----------------------CREATE THE POLYGONS--------------------------#
        num_labels, labels = cv2.connectedComponents(full_mask)

        polygons = []
        #Pull out all the labeled pixels
        for label in range(1, num_labels):  # skip background (0)
            component = (labels == label).astype(np.uint8)

            contours, _ = cv2.findContours(
                component,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            #Stitch pixels into polygons
            for cnt in contours:
                if len(cnt) >= 3:
                    poly = Polygon(cnt.squeeze())
                    polygons.append(poly)


        #Convert Polygons to geospatially informed polygons
        geo_polygons = []
        for geom, value in shapes(full_mask, transform=self.transform):
            if value == 1:
                geo_polygons.append(shape(geom))

        #Push into GeoPandas DF for storage/access
        gdf = gpd.GeoDataFrame(geometry=geo_polygons, crs=self.crs)


        #-----------------------RETURN MASK & POLYGONS--------------------------#
        return full_mask, gdf


#SPECIFICALLY FOR SENTINEL ITEMS
#Class to collect items for a spacific observation area at a given time
class ObservedArea:
    def __init__(self, aoi, datetime):
        self.aoi = aoi
        self.datetime = datetime

        self.get_items()


    #Function to collect the items associated with that area during that time
    def get_items(self):
        self.items = []
        
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier = planetary_computer.sign_inplace)

        #Setup the Search
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            intersects=self.aoi,
            datetime=self.datetime
        )

        #Collect the items and save as class Item in list
        item_names = list(search.get_items())
        for name in item_names: self.items.append(Sentinel_Item(name, self.aoi))





