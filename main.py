import PIL.Image
from PIL.ExifTags import TAGS,GPSTAGS
from PIL import Image
import easygui
from tkinter import *
#
#
path=easygui.fileopenbox()
image=PIL.Image.open(path)


def infromation():
    exif= {
        "Filename": image.filename,
        "Image Size": image.size,
        "Image Height": image.height,
        "Image Width": image.width,
        "Image Format": image.format,
        "Image Mode": image.mode,
        "Image is Animated": getattr(image, "is_animated", False),
        "Frames in Image": getattr(image, "n_frames", 1)
    }

    for label,value in exif.items():
        print(f"{label:25}: {value}")

    exifdata = image.getexif()
    for tag_id in exifdata:
        # get the tag name, instead of human unreadable tag id
        tag = TAGS.get(tag_id, tag_id)
        data = exifdata.get(tag_id)
        # decode bytes
        if isinstance(data, bytes):
            data = data.decode()
        print(f"{tag:25}: {data}")






from exif import Image
from gmplot import gmplot
from geopy.geocoders import Nominatim
import webbrowser
import os
def gpsifo():
    def decimal_coords(coords, ref):
        decimal_degrees = coords[0] + coords[1] / 60 + coords[2] / 3600
        if ref == 'S' or ref == 'W':
            decimal_degrees = -decimal_degrees
        return decimal_degrees

    filename = path
    input = f'{filename}'
    output = f'{filename}-location.html'


    with open(input, 'rb') as src:
        img = Image(src)

    lat = decimal_coords(img.gps_latitude, img.gps_latitude_ref)
    lon = decimal_coords(img.gps_longitude, img.gps_longitude_ref)


    gmap = gmplot.GoogleMapPlotter(lat, lon, 12)
    gmap.marker(lat, lon, 'red')
    gmap.draw(output)

    address = Nominatim(user_agent='GetLoc')
    location = address.reverse(f'{lat}, {lon}')


    gpsifo.ad=location.address

    print(location.address)




    webbrowser.open(f'file:///{os.getcwd()}/{output}', new=1)


try:
    gpsifo()

except:
    pass
    print('not GPS Found')
finally:
    infromation()














