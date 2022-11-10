from flask import Flask, request, jsonify
from landsatxplore.api import API
from landsatxplore.earthexplorer import EarthExplorer
import glob, os, rasterio, tarfile
from osgeo import gdal

app = Flask(__name__)

def landsatExplorerLogin():
    api = API(os.getenv('LANDSATXPLORE_USERNAME'), os.getenv('LANDSATXPLORE_PASSWORD'))
    return api

def earthExplorerLogin():
    ee = EarthExplorer(os.getenv('LANDSATXPLORE_USERNAME'), os.getenv('LANDSATXPLORE_PASSWORD'))
    return ee

def metadato(urlArchivo):
    archivo=open(urlArchivo,"r")  
    metadatos={}                            
    for i in archivo.readlines():           
        if "=" in i:                       
            separador = i.split("=")       
            clave = separador[0].strip()     
            valor = separador[1].strip()      
            metadatos[clave] = valor          
    archivo.close()
    return metadatos

def guardar_tif(salida,matriz,im_entrada,x_in=0,y_in=0):
    #definir coordenadas iniciales 
    geoTs=im_entrada.GetGeoTransform()
    driver=gdal.GetDriverByName("GTiff")
    prj=im_entrada.GetProjection()
    cols=matriz.shape[1]
    filas=matriz.shape[0]
    ulx=geoTs[0]+x_in*geoTs[1]
    uly=geoTs[3]+y_in*geoTs[5]
    geoTs=(ulx,geoTs[1],geoTs[2],uly,geoTs[4],geoTs[5])
    #Crear el espacio para escribir los datos de la matriz a la imagen de salida
    export=driver.Create(salida,cols,filas,1,gdal.GDT_Float32)
    banda=export.GetRasterBand(1)
    banda.WriteArray(matriz)
    export.SetGeoTransform(geoTs)
    export.SetProjection(prj)
    banda.FlushCache()
    export.FlushCache()


@app.route('/', methods=['GET'])
def main():
    return 'Hola server'

@app.route('/pruebaeos/catalogo', methods=['POST'])
def catalogo():
    try:
        data = request.json
        api = landsatExplorerLogin()
        scenes = api.search(
            dataset=data["dataset"],
            latitude=float(data["lat"]),
            longitude=float(data["lon"]),
            start_date=data["fecha_inicio"],
            end_date=data["fecha_fin"],
            max_cloud_cover=int(data["nubosidad_max"])
        )
        api.logout()
        if len(scenes) == 0:
            return 'No se encontraron resultados con los filtros establecidos'
        else:
            escenas = [ { "fecha": scene["date_l1_generated"], "identificador": scene["displayId"] } for scene in scenes ]
            response = {
                "escenas": escenas,
                "escenas_encontradas": len(scenes),
            }
            return jsonify(response)
    except:
        return 'no se pudo efectuar el proceso'

@app.route('/pruebaeos/descarga', methods=['POST'])
def descarga():
    try:
        data = request.json
        url = "http://localhost:5000/pruebaeos"+data["output_dir"].replace(".","")+'/'+data["escena"]
        if "accion" in data:
            if data["accion"] == "descarga":
                zipPath = data["output_dir"]+'/'+data["escena"]
                if not os.path.exists(data["output_dir"]):
                    os.mkdir(data["output_dir"])

                ee = earthExplorerLogin()
                ee.download(data["escena"], output_dir=data["output_dir"])
                ee.logout()

                file = tarfile.open(zipPath+'.tar.gz')
                os.mkdir(zipPath)
                file.extractall(zipPath)
                file.close()
                response = {
                    "escena": data["escena"],
                    "url": url
                }
                os.remove(zipPath+'.tar.gz')
                return jsonify(response)
            elif data["accion"] == "listar":
                if os.path.exists(data["output_dir"]):
                    response = {
                        "escena": data["escena"],
                        "url": url,
                        "archivos": []
                    }
                    archivos = {}
                    for index, file in enumerate(glob.glob(data["output_dir"]+'/'+data["escena"]+'/'+"*.TIF")):
                        if("BQA" not in file):
                            value = file.replace(data["output_dir"]+'/'+data["escena"]+'/', "")
                            llave = "banda"+value.replace(data["escena"]+"_B", "").replace(".TIF","")
                            archivos[llave] = value
                    response["archivos"].append(archivos)
                    return jsonify(response)
                else :
                    response = {
                        "escena": data["escena"],
                        "mensaje" : "escena no encontrada"
                    }
                    return jsonify(response)
            else:
                return 'Acción no válida'
        else:
            return 'Debe digitar la acción'
    except:
        return 'no se pudo efectuar el proceso'

@app.route('/pruebaeos/ndvi', methods=['POST'])
def ndvi():
    try:
        # variables
        ndvi = None
        data = request.json
        latitud = float(data["lat"])
        longitud = float(data["lon"])
        folderPath = data["output_dir"]+'/'+data["escena"]+'/'
        archivo_mtl = metadato(folderPath+data["escena"]+'_MTL.txt')

        # para landsat 8
        if(eval(archivo_mtl["SPACECRAFT_ID"]) == "LANDSAT_8"):
            numberBands = [4, 5]
            rasterObj = {}
            for band in numberBands:
                ruta = folderPath+data["escena"]+'_B'+str(band)+'.TIF'
                rasterObj[str(band)] = (rasterio.open(ruta).read()).astype(float)
            ndvi = (rasterObj["5"]-rasterObj["4"]) / (rasterObj["5"]+rasterObj["4"])

        # para el resto
        else:
            numberBands = [3, 4]
            rasterObj = {}
            for band in numberBands:
                ruta = folderPath+data["escena"]+'_B'+str(band)+'.TIF'
                rasterObj[str(band)] = (rasterio.open(ruta).read()).astype(float)
            ndvi = (rasterObj["4"]-rasterObj["3"]) / (rasterObj["4"]+rasterObj["3"])

        # calculo de ndvi por ubicación
        p, m, n = ndvi.shape
        guardar_tif(folderPath+'ndvi.tif', ndvi.reshape(m,n), gdal.Open(ruta))
        warp = gdal.Warp(folderPath+'ndvi.tif',gdal.Open(folderPath+'ndvi.tif'),dstSRS='EPSG:4326')
        warp = None
        ndvi = rasterio.open(folderPath+'ndvi.tif')
        ndviResult = []
        [ ndviResult.append(value.item(0)) for value in ndvi.sample([(longitud, latitud)]) ]
        response = {
            "ndvi": ndviResult[0]
        }
        os.remove(folderPath+'ndvi.tif')
        return jsonify(response)

    except:
        return 'No se pudo calcular el valor de NDVI'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)