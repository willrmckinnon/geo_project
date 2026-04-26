from utils import helper
from data.load_planetary_comp_data import Sentinel_Item, ObservedArea
from datetime import datetime, timedelta
from models.load_model import load_model

import rasterio.plot as rplt
import matplotlib.pyplot as plt

def main():
    config = helper.load_config()
    INPUT = config['Input']

    #Setup the Datetime
    date_obj = datetime.strptime(INPUT['date'], "%Y-%m-%d").date()
    today = str(date_obj)
    delay = str(date_obj - timedelta(days=20))
    DATETIME = delay + '/' + today

    #Setup the AOI
    lat, lon = INPUT['HOME']
    aoi = helper.point_to_polygon(lat, lon, dim = 4000)

    #Collect the first item
    obs = ObservedArea(aoi, DATETIME)
    item1 = obs.items[1]

    #Setup the Model
    model = load_model(INPUT['model_path'])

    #Collect the image and building data
    image = item1.get_array()
    mask, gdf = item1.get_buildings(model)


    #Display the image and buildings
    fig, ax = plt.subplots(figsize=(10, 10))
    rplt.show(image, transform=item1.transform, ax=ax)

    # plot directly in geospatial space
    gdf.boundary.plot(ax=ax, color="red", linewidth=2)
    gdf.plot(ax=ax, color="red", alpha=0.2)

    plt.axis("off")
    plt.show()







if __name__ == "__main__":
    main()