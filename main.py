from utils import helper
from data.load_planetary_comp_data import Sentinel_Item, ObservedArea
from datetime import datetime, timedelta
from models.load_model import load_model

import rasterio.plot as rplt
import matplotlib.pyplot as plt
import argparse
from PIL import Image

def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--loc", type=str, required=False)
    parser.add_argument("--lat", type=float, required=False)
    parser.add_argument("--lon", type=float, required=False)
    parser.add_argument("--date", type=float, required=False)

    return parser.parse_args()


def main():
    args = get_args()
    config = helper.load_config()

    #Setup the Datetime
    #If no input argument is given, start with today
    if args.date: date_obj = datetime.strptime(args.date, "%Y-%m-%d").date()
    else: date_obj = datetime.now().date()
    start_day = str(date_obj) #Calculate the start and end dates
    delay = str(date_obj - timedelta(days=20))
    DATETIME = delay + '/' + start_day #Configure in a format for retrieval

    #Setup the AOI
    if args.lat and args.lon:
        lat, lon = args.lat, args.lon
    elif args.loc:
        lat,lon = config['known_locations'][args.loc]
    else:   
        lat, lon = config['known_locations']['dc']
    aoi = helper.point_to_polygon(lat, lon, dim = 8000)

    print("Started - Fetching Data")
    #Collect the first item
    obs = ObservedArea(aoi, DATETIME)
    item1 = obs.items[1]

    #Setup the Model
    model = load_model(config['model_path'])
    print("Model Setup - Identifying Buildings")

    #Collect the image and building data
    image = item1.get_visual()
    mask, gdf = item1.get_buildings(model)


    #Display image and polygons on slider
    overlay = helper.polygons_to_overlay(gdf['geometry'], [image.height, image.width], item1.transform)

    print("Displaying Image")
    helper.image_slider(overlay, image)








if __name__ == "__main__":
    main()