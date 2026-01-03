import urllib.request
import os

os.makedirs("models", exist_ok=True)

models = {
    "FSRCNN_x4.pb": "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x4.pb",
    "EDSR_x4.pb": "https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x4.pb"
}

print("Downloading models...")
for name, url in models.items():
    print(f"Downloading {name}...")
    try:
        urllib.request.urlretrieve(url, f"models/{name}")
        print("Done.")
    except Exception as e:
        print(f"Failed to download {name}: {e}")
