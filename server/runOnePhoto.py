from objectDetection import objectDetection
import cv2

objectDetection = objectDetection()

def testDevice(source):
   cap = cv2.VideoCapture()
   cap.open(source, cv2.CAP_DSHOW)
   if cap is None or not cap.isOpened():
       print('Warning: unable to open video source: ', source)
   else:
       print('OK: ', source)
       while (True):
           ret, frame = cap.read()
           img, detections = objectDetection.detection(frame)
           if cv2.waitKey(1) & 0xFF == ord('q'):
               break
           print(detections)
testDevice(0)