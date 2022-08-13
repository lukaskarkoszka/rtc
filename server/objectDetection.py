import cv2
import numpy as np
from elements.yolo import OBJ_DETECTION
import time

class objectDetection():
    def __init__(self):
        classesFile = "coco.names"
        with open(classesFile, 'rt') as f:
            self.classes = f.read().rstrip('\n').split('\n')

        self.Object_colors = list(np.random.rand(80, 3) * 255)
        self.Object_detector = OBJ_DETECTION('weights/yolov5s.pt', self.classes)

    def detection(self, img):
        start_time = time.clock()
        detections = self.Object_detector.detect(img)

        for detection in detections:
            # print(obj)
            label = detection['label']
            score = detection['score']
            [(xmin, ymin), (xmax, ymax)] = detection['bbox']
            color = self.Object_colors[self.classes.index(label)]
            img = cv2.rectangle(img, (xmin, ymin), (xmax, ymax), color, 2)
            img = cv2.putText(img, f'{label} ({str(score)})', (xmin, ymin), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color,
                                1, cv2.LINE_AA)

        #print(time.clock() - start_time, "seconds")
        return img, detections
