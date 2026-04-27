import yaml

from shapely.geometry import box
from pyproj import Transformer

import tkinter as tk
from PIL import Image, ImageTk,  ImageDraw



#Reads the config file
def load_config():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    return config


#converts a point to a polygon
def point_to_polygon(lat, lon, dim=4000):
    # WGS84 → Web Mercator (meters)
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    # convert center point to meters
    x, y = to_m.transform(lon, lat)

    half_size = dim/2 

    # create square in meters
    square = box(
        x - half_size, y - half_size,
        x + half_size, y + half_size
    )

    # convert back to WGS84
    coords = [
        list(to_wgs.transform(px, py))
        for px, py in square.exterior.coords
    ]

    return {
        "type": "Polygon",
        "coordinates": [coords]
    }


#Converts a set of polygons to a PIL Image Overlay
def polygons_to_overlay(polygons, shape, transform):
    """
    Returns an RGBA image with polygons drawn on transparent background
    """
    height, width = shape[0], shape[1]

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    inv_transform = ~transform

    def geo_to_pixel(x, y):
        col, row = inv_transform * (x, y)
        col = max(0, min(width - 1, col))
        row = max(0, min(height - 1, row))
        return((col, row))

    for poly in polygons:
        if poly.is_empty:
            continue

        #Convert the polygon outline to pixels
        coords = [geo_to_pixel(x, y) for x, y in poly.exterior.coords]

        #Draw those pixels to the overlay
        draw.polygon(coords, outline=(255, 0, 0, 255), fill=(255, 0, 0, 80))

    return overlay



#Sliding App that shows Top image over Base Image
#Both should be PIL Images
def image_slider(img1, img2):
    # Ensure same size
    w = min(img1.width, img2.width)
    h = min(img1.height, img2.height)
    img1 = img1.resize((w, h))
    img2 = img2.resize((w, h))

    #Then increase size of both for a better picture
    aspect = w / h
    target_w = 800 #800 pixel height
    target_h = (int)(target_w / aspect)
    img1 = img1.resize((target_w, target_h), Image.Resampling.BILINEAR)
    img2 = img2.resize((target_w, target_h), Image.Resampling.BILINEAR)



    root = tk.Tk()
    root.title("Image Slider")

    canvas = tk.Canvas(root, width=target_w, height=target_h)
    canvas.pack()

    # Convert to Tk format
    tk_img1 = ImageTk.PhotoImage(img1)
    tk_img2 = ImageTk.PhotoImage(img2)

    # Base image (bottom)
    canvas.create_image(0, 0, anchor="nw", image=tk_img2)

    # Top image (will be cropped dynamically)
    top_img_id = canvas.create_image(0, 0, anchor="nw")

    def update_slider(x):
        x = int(float(x))

        # Crop left portion of top image
        cropped = img1.crop((0, 0, x, target_h))
        tk_crop = ImageTk.PhotoImage(cropped)

        # Update canvas image
        canvas.itemconfig(top_img_id, image=tk_crop)
        canvas.image = tk_crop  # prevent garbage collection

    # Slider
    slider = tk.Scale(
        root,
        from_=0,
        to=target_w,
        orient="horizontal",
        command=update_slider
    )
    slider.pack(fill="x")

    # Initialize at middle
    slider.set(target_w // 2)

    root.mainloop()

