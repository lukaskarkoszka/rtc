import cv2


class objectTracking:

        def __init__(self):
            self.tracker = cv2.TrackerCSRT_create()

        def initialize(self, img, CLICK):
            bbox = CLICK.split('"')[5].split(',')
            for i in range(len(bbox)):
                bbox[i] = int(bbox[i])
            bbox = tuple(bbox)
            self.tracker.init(img, bbox)

            return True


        def tracking(self, img):
            ok, bbox = self.tracker.update(img)
            cv2.putText(img, "Tracking", (100, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 0, 0), 2)
            if not ok:
                bbox = None

            return bbox