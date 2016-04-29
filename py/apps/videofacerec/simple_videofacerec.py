#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) Philipp Wagner. All rights reserved.
# Licensed under the BSD license. See LICENSE file in the project root for full license information.

import logging
from Queue import Queue
from threading import Thread
# cv2 and helper:
import cv2
from imutils import paths
from helper.common import *
from helper.video import *
# add facerec to system path
import sys
sys.path.append("../..")
# facerec imports
from facerec.lbp import ExtendedLBP
from facerec.model import PredictableModel
from facerec.feature import Fisherfaces, SpatialHistogram 
from facerec.distance import EuclideanDistance, ChiSquareDistance
from facerec.classifier import NearestNeighbor
from facerec.validation import KFoldCrossValidation
from facerec.serialization import save_model, load_model
# for face detection (you can also use OpenCV2 directly):
from facedet.detector import CascadedDetector
import numpy as np
import random
import time
import pyttsx
import subprocess
from gtts import gTTS
import os.path
import math
import numpy 
import Image

voiceq = Queue(maxsize=0)
vnum_threads = 1

def speak(voiceq):
  while True:
    if voiceq.qsize() > 0:
      name = voiceq.get()
      audio_file = "audio/"+name.replace(" ", "_")+".mp3"
      if not os.path.isfile(audio_file):  # Check if we already have the file saved so we don't pass it to google
        print("Audio doesn't exist, Calling to Google")
        tts = gTTS(text=name, lang="en")
        tts.save(audio_file)
      else:
         print("Audio Exists. Skipping Google")
      return_code = subprocess.Popen(["mpg123", audio_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      return_code.wait()
      voiceq.task_done()

class ExtendedPredictableModel(PredictableModel):
    """ Subclasses the PredictableModel to store some more
        information, so we don't need to pass the dataset
        on each program call...
    """

    def __init__(self, feature, classifier, image_size, subject_names):
        PredictableModel.__init__(self, feature=feature, classifier=classifier)
        self.image_size = image_size
        self.subject_names = subject_names

def get_model(image_size, subject_names):
    """ This method returns the PredictableModel which is used to learn a model
        for possible further usage. If you want to define your own model, this
        is the method to return it from!
    """
    # Define the Fisherfaces Method as Feature Extraction method:
    feature = Fisherfaces()
    # Define a 1-NN classifier with Euclidean Distance:
    classifier = NearestNeighbor(dist_metric=EuclideanDistance(), k=1)
    # Return the model as the combination:
    return ExtendedPredictableModel(feature=feature, classifier=classifier, image_size=image_size, subject_names=subject_names)

def read_subject_names(path):
    """Reads the folders of a given directory, which are used to display some
        meaningful name instead of simply displaying a number.

    Args:
        path: Path to a folder with subfolders representing the subjects (persons).

    Returns:
        folder_names: The names of the folder, so you can display it in a prediction.
    """
    folder_names = []
    for dirname, dirnames, filenames in os.walk(path):
        for subdirname in dirnames:
            folder_names.append(subdirname)
    return folder_names

def read_images(path, image_size=None):
    """Reads the images in a given folder, resizes images on the fly if size is given.

    Args:
        path: Path to a folder with subfolders representing the subjects (persons).
        sz: A tuple with the size Resizes 

    Returns:
        A list [X, y, folder_names]

            X: The images, which is a Python list of numpy arrays.
            y: The corresponding labels (the unique number of the subject, person) in a Python list.
            folder_names: The names of the folder, so you can display it in a prediction.
    """
    c = 0
    X = []
    y = []
    folder_names = []
    for dirname, dirnames, filenames in os.walk(path):
        for subdirname in dirnames:
            folder_names.append(subdirname)
            subject_path = os.path.join(dirname, subdirname)
            for filename in os.listdir(subject_path):
                try:
                    im = cv2.imread(os.path.join(subject_path, filename), cv2.IMREAD_GRAYSCALE)
                    # resize to given size (if given)
                    if (image_size is not None):
                      try:
                        im = cv2.resize(im, image_size)
                      except:
                        print "Image {0}/{1} bad. Please delete...".format(subject_path, filename)
                        raise
                    X.append(np.asarray(im, dtype=np.uint8))
                    y.append(c)
                except IOError, (errno, strerror):
                    print "I/O error({0}): {1}".format(errno, strerror)
                except:
                    print "Unexpected error:", sys.exc_info()[0]
                    raise
            c = c+1
    return [X,y,folder_names]

def makeModel(voiceq, dataset='pictures/', image_size=(100, 100), model_filename='my_model.pkl'):
  global reloadModel
  modelReload = time.time()
  while True:
    if modelReload < time.time() - 600:  # Remodel after 10 minutes, in case we have new photos
      voiceq.put("Remodeling faces")
      # Check if the given dataset exists:
      if not os.path.exists(dataset):
        print "[Error] No dataset found at '%s'." % dataset_path
        sys.exit()    
      # Reads the images, labels and folder_names from a given dataset. Images
      # are resized to given size on the fly:
      print "Loading dataset..."
      #image_size = (int(image_size.split("x")[0]), int(image_size.split("x")[1]))
      [images, labels, subject_names] = read_images(dataset, image_size)
      # Zip us a {label, name} dict from the given data:
      list_of_labels = list(xrange(max(labels)+1))
      subject_dictionary = dict(zip(list_of_labels, subject_names))
      # Get the model we want to compute:
      model = get_model(image_size=image_size, subject_names=subject_dictionary)
      # Sometimes you want to know how good the model may perform on the data
      # given, the script allows you to perform a k-fold Cross Validation before
      # the Detection & Recognition part starts:
      # Compute the model:
      print "Computing the model..."
      model.compute(images, labels)
      # And save the model, which uses Pythons pickle module:
      print "Saving the model..."
      save_model(model_filename, model)
      modelReload = time.time()
      reloadModel = True
    time.sleep(1)

class App(object):
    def __init__(self, camera_id, cascade_filename):
        self.detector = CascadedDetector(cascade_fn=cascade_filename, minNeighbors=5, scaleFactor=1.1)
        self.cam = create_capture(camera_id)
            
    def run(self):
        global reloadModel
        reloadModel = True
        for i in range(vnum_threads):
          worker = Thread(target=speak, args=(voiceq,))
          worker.setDaemon(True)
          worker.start()
        whosHere = {}
        oldLoc = {}  #Tracking persons old location
        foundPerson = None
        t1 = Thread(target=makeModel, args=(voiceq,))
        t1.setDaemon(True)
        t1.start()
        while True:
            if reloadModel is True:
              print "Loading the model..."
              model = load_model(model_filename)
              reloadModel = False
            self.model = model
            ret, frame = self.cam.read()
            # Resize the frame to half the original size for speeding up the detection process:
            img = cv2.resize(frame, (frame.shape[1]/2, frame.shape[0]/2), interpolation = cv2.INTER_CUBIC)
            # Clean up image contrast automatically
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            img = clahe.apply(cv2.cvtColor(img,cv2.COLOR_BGR2GRAY))
            imgout = img.copy()
            # See if we've found someone
            if self.detector.detect(img).size == 0:
              foundPerson = None
            else:
              for i,r in enumerate(self.detector.detect(img)):
                  marker = ""
                  x0,y0,x1,y1 = r
                  # (1) Get face, (2) Convert to grayscale & (3) resize to image_size:
                  face = img[y0:y1, x0:x1]
                  face = cv2.resize(face, self.model.image_size, interpolation = cv2.INTER_CUBIC)
                  blurLevel = cv2.Laplacian(face, cv2.CV_64F).var()
                  # Get a prediction from the model:
                  predInfo = self.model.predict(face)
                  distance = predInfo[1]['distances'][0]
                  prediction = predInfo[0]
                  if distance > 200: #and not trainName:
                     foundPerson = 'Unknown'
                     if blurLevel > 400:
                       cv2.imwrite("faces/"+str(time.time())+".jpg", face)
                  else:
                     foundPerson = self.model.subject_names[prediction]
                  if len(oldLoc) > 0 and distance > 200:  # Determine person with heuristics based on last location
                    for key,value in oldLoc.iteritems():
                       if np.isclose(value, r, atol=50.0).all() and foundPerson != key:  # Within 50 pixels of any direction
                         # Make sure we don't already have enough photos of this person... limit 200 and the image isn't toooooooo blurry. 
                         DIR = "pictures/"+key
                         if os.path.isdir(DIR):
                           personImgCount = len([name for name in os.listdir(DIR) if os.path.isfile(os.path.join(DIR, name))])
                           if personImgCount < 100 and blurLevel > 600:  # blurLevel higher the better
                             cv2.imwrite(DIR+"/"+str(time.time())+".jpg", face)
                         foundPerson = key
                         marker = "*"
                  if foundPerson not in whosHere.keys() and foundPerson != 'Unknown':
                    voiceq.put("Hello "+foundPerson)
                  whosHere.update({foundPerson:str(time.time())})
                  # Draw the face area in image:
                  cv2.rectangle(imgout, (x0,y0),(x1,y1),(0,255,0),2)
                  # Draw the predicted name (folder name...):
                  draw_str(imgout, (x0,y0-5), foundPerson+marker+" "+str(round(distance,0)))
                  if foundPerson != 'Unknown':
                    oldLoc.update({foundPerson:r})  # Update old person location for heuristics
            checkHere = whosHere.copy()
            for key, value in checkHere.iteritems():  # Check when we last saw someone and remove if longer than 10 seconds.
              if float(value) < (time.time() - 5):
                del whosHere[key]
                if key != 'Unknown':  # oldLoc doesn't ever contain Unknown, because we're aiming to eliminate unknowns.
                  del oldLoc[key]
            i = str(whosHere.keys())
            draw_str(imgout, (1, frame.shape[0]/2 - 5), str(whosHere.keys()))  # drop string of who's seen
            cv2.imshow('Jarvis 0.4a', imgout)
            # Show image & exit on escape:
            ch = cv2.waitKey(1)
            if ch == 27:
                break
            voiceq.join()


if __name__ == '__main__':
    from optparse import OptionParser
    # model.pkl is a pickled (hopefully trained) PredictableModel, which is
    # used to make predictions. You can learn a model yourself by passing the
    # parameter -d (or --dataset) to learn the model from a given dataset.
    usage = "usage: %prog [options] model_filename"
    # Add options for training, resizing, validation and setting the camera id:
    parser = OptionParser(usage=usage)
    parser.add_option("-r", "--resize", action="store", type="string", dest="size", default="100x100", 
        help="Resizes the given dataset to a given size in format [width]x[height] (default: 100x100).")
    parser.add_option("-v", "--validate", action="store", dest="numfolds", type="int", default=None, 
        help="Performs a k-fold cross validation on the dataset, if given (default: None).")
    parser.add_option("-t", "--train", action="store", dest="dataset", type="string", default=None,
        help="Trains the model on the given dataset.")
    parser.add_option("-i", "--id", action="store", dest="camera_id", type="int", default=0, 
        help="Sets the Camera Id to be used (default: 0).")
    parser.add_option("-c", "--cascade", action="store", dest="cascade_filename", default="haarcascade_frontalface_alt2.xml",
        help="Sets the path to the Haar Cascade used for the face detection part (default: haarcascade_frontalface_alt2.xml).")
    # Show the options to the user:
    parser.print_help()
    print "Press [ESC] to exit the program!"
    print "Script output:"
    # Parse arguments:
    (options, args) = parser.parse_args()
    # Check if a model name was passed:
    if len(args) == 0:
        print "[Error] No prediction model was given."
        sys.exit()
    # This model will be used (or created if the training parameter (-t, --train) exists:
    model_filename = args[0]
    # Check if the given model exists, if no dataset was passed:
    if (options.dataset is None) and (not os.path.exists(model_filename)):
        print "[Error] No prediction model found at '%s'." % model_filename
        sys.exit()
    # Check if the given (or default) cascade file exists:
    if not os.path.exists(options.cascade_filename):
        print "[Error] No Cascade File found at '%s'." % options.cascade_filename
        sys.exit()
    # We are resizing the images to a fixed size, as this is neccessary for some of
    # the algorithms, some algorithms like LBPH don't have this requirement. To 
    # prevent problems from popping up, we resize them with a default value if none
    # was given:
    try:
        image_size = (int(options.size.split("x")[0]), int(options.size.split("x")[1]))
    except:
        print "[Error] Unable to parse the given image size '%s'. Please pass it in the format [width]x[height]!" % options.size
        sys.exit()
    # We have got a dataset to learn a new model from:
    if options.dataset:
        # Check if the given dataset exists:
        if not os.path.exists(options.dataset):
            print "[Error] No dataset found at '%s'." % dataset_path
            sys.exit()    
        # Reads the images, labels and folder_names from a given dataset. Images
        # are resized to given size on the fly:
        print "Loading dataset..."
        [images, labels, subject_names] = read_images(options.dataset, image_size)
        # Zip us a {label, name} dict from the given data:
        list_of_labels = list(xrange(max(labels)+1))
        subject_dictionary = dict(zip(list_of_labels, subject_names))
        # Get the model we want to compute:
        model = get_model(image_size=image_size, subject_names=subject_dictionary)
        # Sometimes you want to know how good the model may perform on the data
        # given, the script allows you to perform a k-fold Cross Validation before
        # the Detection & Recognition part starts:
        if options.numfolds:
            print "Validating model with %s folds..." % options.numfolds
            # We want to have some log output, so set up a new logging handler
            # and point it to stdout:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            # Add a handler to facerec modules, so we see what's going on inside:
            logger = logging.getLogger("facerec")
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            # Perform the validation & print results:
            crossval = KFoldCrossValidation(model, k=options.numfolds)
            crossval.validate(images, labels)
            crossval.print_results()
        # Compute the model:
        print "Computing the model..."
        model.compute(images, labels)
        # And save the model, which uses Pythons pickle module:
        print "Saving the model..."
        save_model(model_filename, model)
    # Now it's time to finally start the Application! It simply get's the model
    # and the image size the incoming webcam or video images are resized to:
    print "Starting application..."
    App(camera_id=options.camera_id,
        cascade_filename=options.cascade_filename).run()
