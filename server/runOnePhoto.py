from objectDetection import objectDetection
import cv2

img=cv2.imread('ludzie.jpg')

objectDetection = objectDetection()
img = objectDetection.detection(img)
cv2.imshow("CSI Camera", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
