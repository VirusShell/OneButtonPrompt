import json
import requests
import io
import base64
import uuid
import sys, os
from PIL import Image, PngImagePlugin
from model_lists import *
import time

def call_txt2img(passingprompt,ratio,upscale,debugmode,filename="",model = "currently selected model",samplingsteps = "40",cfg= "7",hiressteps ="0",denoisestrength="0.6",samplingmethod="DPM++ SDE Karras", upscaler="R-ESRGAN 4x+",hiresscale="2",apiurl="http://127.0.0.1:7860", qualitygate=False,quality="7.6",runs="5",negativeprompt=""):

    #set the prompt!
    prompt = passingprompt
    checkprompt = passingprompt.lower()

    #set the URL for the API
    url = apiurl

    #rest of prompt things
    sampler_index = samplingmethod
    steps = samplingsteps
    if(debugmode==1):
        steps="10"
    cfg_scale = cfg

    #size
    if(ratio=='wide'):
        width = "768"
        height = "512"
    elif(ratio=='portrait'):
        width = "512"
        height = "768"
    elif(ratio=='ultrawide'):
        width = "1280"
        height = "360"
    else:
        width = "512"
        height = "512"
    #upscaler
    enable_hr = upscale
    if(debugmode==1):
        enable_hr="False"
    
    #defaults
    hr_scale = hiresscale
    denoising_strength = denoisestrength
    
    hr_second_pass_steps = hiressteps
    #hr_upscaler = "LDSR" # We have the time, why not use LDSR

    if(upscaler != "automatic"):
        hr_upscaler = upscaler
    else:
        upscalerlist = get_upscalers()
        # on automatic, make some choices about what upscaler to use
        # photos, prefer 4x ultrasharp
        # anime, cartoon or drawing, go for R-ESRGAN 4x+ Anime6B
        # else, R-ESRGAN 4x+"
        if("hoto" in checkprompt and "4x-UltraSharp" in upscalerlist):
            hr_upscaler = "4x-UltraSharp"
        elif("anime" in checkprompt or "cartoon" in checkprompt or "draw" in checkprompt or "vector" in checkprompt or "cel shad" in checkprompt or "visual novel" in checkprompt):
            hr_upscaler = "R-ESRGAN 4x+ Anime6B"
        else:
            hr_upscaler = "R-ESRGAN 4x+"

        if(hiressteps==0):
            hiressteps = samplingsteps
        hr_second_pass_steps = int(hiressteps/2)

        hr_scale = 2
        
        if(hr_upscaler== "4x-UltraSharp"):
            denoising_strength = "0.35"
        if(hr_upscaler== "R-ESRGAN 4x+ Anime6B+"):
            denoising_strength = "0.6" # 0.6 is fine for the anime upscaler
        if(hr_upscaler== "R-ESRGAN 4x+"):
            denoising_strength = "0.5" # default 0.6 is a lot and changes a lot of details
            

    #params to stay the same

    script_dir = os.path.dirname(os.path.abspath(__file__))  # Script directory
    outputTXT2IMGfolder = os.path.join(script_dir, "./automated_outputs/txt2img/")
    if(filename==""):
        filename = str(uuid.uuid4())
    
    outputTXT2IMGpng = '.png'
    #outputTXT2IMGFull = '{}{}{}'.format(outputTXT2IMGfolder,filename,outputTXT2IMGpng)
    outputTXT2IMGtxtfolder = os.path.join(script_dir, "./automated_outputs/prompts/")
    outputTXT2IMGtxt = '.txt'
    outputTXT2IMGtxtFull = '{}{}{}'.format(outputTXT2IMGtxtfolder,filename,outputTXT2IMGtxt)

    # params for quality gate
    isGoodNumber = float(quality)
    foundgood = False
    MaxRuns = int(runs)
    Runs = 0
    scorelist = []
    scoredeclist = []
    imagelist = []
    pnginfolist = []


    #call TXT2IMG

    payload = {
        "prompt": prompt,
        "sampler_index": sampler_index,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "width": width,
        "height": height,
        "enable_hr": enable_hr,
        "denoising_strength": denoising_strength,
        "hr_scale": hr_scale,
        "hr_upscaler": hr_upscaler,
        "hr_second_pass_steps": hr_second_pass_steps
    }

    if(model != "currently selected model"):
        payload.update({"sd_model": model})
    
    if(negativeprompt != ""):
        payload.update({"negative_prompt": negativeprompt})

    while Runs < MaxRuns:

        # make the filename unique for each run _0, _1, etc.
        addrun = "_" + str(Runs)
        filenamefull = filename + addrun
        outputTXT2IMGFull = '{}{}{}'.format(outputTXT2IMGfolder,filenamefull,outputTXT2IMGpng)

        r = []
        
        # If we don't get an image back, we want to retry a few times. Max 3 times
        for i in range(4):
            response = requests.post(url=f'{url}/sdapi/v1/txt2img', json=payload)

            r = response.json()
            if('images' in r):
                break # this means if we have the images object, then we "break" out of the for loop.
            else:
                if(i == 3):
                    print("If this keeps happening: Is WebUI started with --api enabled?")
                    print("")
                    raise ValueError("API has not been responding after several retries. Stopped processing.")
                print("")
                print("We haven't received an image from the API. Maybe something went wrong. Will retry after waiting a bit.")
                

                time.sleep(10 * (i+1) ) # incremental waiting time




        for i in r['images']:
            image = Image.open(io.BytesIO(base64.b64decode(i.split(",",1)[0])))

            png_payload = {
                "image": "data:image/png;base64," + i
            }
            response2 = requests.post(url=f'{url}/sdapi/v1/png-info', json=png_payload)

            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("parameters", response2.json().get("info"))
            image.save(outputTXT2IMGFull, pnginfo=pnginfo)

            if(qualitygate==True):
                # check if the file exists in the parent directory
                imagescorer_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'stable-diffusion-webui-aesthetic-image-scorer', 'scripts'))
                #print(imagescorer_path)
                if imagescorer_path not in sys.path:
                    sys.path.append(imagescorer_path)      
                try:
                    
                    import image_scorer
                    print("Found aesthetic-image-scorer! Using this to measure the results...")
                    score = image_scorer.get_score(image)
                    scoredeclist.append(score)
                    score = round(score,1)

                    scorelist.append(score)
                    imagelist.append(outputTXT2IMGFull)
                    pnginfolist.append(pnginfo)

                    print("This image has scored: "+ str(score) + " out of " + str(isGoodNumber))
                    if(score >= isGoodNumber or debugmode == 1):
                        foundgood = True
                        print("Yay its good! Keeping this result.")
                    else:
                        runstodo = MaxRuns - Runs - 1
                        print("Not a good result. Retrying for another " + str(runstodo) + " times or until the image is good enough.")
                        
                except ImportError:
                    foundgood = True # just continue :)

                    # handle the case where the module doesn't exist
                    print("Could not find the stable-diffusion-webui-aesthetic-image-scorer extension.")
                    print("Install this extension via the WebUI to use Quality Gate")
                    pass
            else:
                foundgood = True # If there is no quality gate, then everything is good. So we escape this loop
            
        Runs += 1
        if(foundgood == True):
            break #Break the loop if we found something good. Or if we set it to good :)

    if(len(imagelist) > 0):

        if(foundgood == True):
            print("Removing any other images generated this run (if any).")
        else:
            print("Stopped trying, keeping the best image we had so far.")

        # Get the index of the first occurrence of the maximum value in the list
        indexofimagetokeep = scoredeclist.index(max(scoredeclist))
        outputTXT2IMGFull = imagelist[indexofimagetokeep] #store the image to keep in here, so we can pass it along
        pnginfo = pnginfolist[indexofimagetokeep]
        imagelist.pop(indexofimagetokeep)  
        #remove all other images
        for imagelocation in imagelist:
            os.remove(imagelocation)


    with open(outputTXT2IMGtxtFull,'w',encoding="utf8") as txt:
        json_object = json.dumps(payload, indent = 4)
        txt.write(json_object)

    return [outputTXT2IMGFull,pnginfo]