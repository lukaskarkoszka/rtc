import cv2


class objectTracking:

        def __init__(self):
            self.tracker = cv2.TrackerCSRT_create()

        def initialize(self, img, CLICK):
            org_h, org_w, _ = img.shape
            img = cv2.resize(img, (320, 160))
            bbox = CLICK.split('"')[5].split(',')
            for i in range(len(bbox)):
                bbox[i] = int(bbox[i])
            bbox = tuple(bbox)
            bbox = (int(bbox[0]), int(bbox[1]), int(bbox[2]-bbox[0]), int(bbox[3]-bbox[1]))
            bbox = (int(bbox[0] * 320 / org_w), int(bbox[1] * 160 / org_h), int(bbox[2] * 320 / org_w), int(bbox[3] * 160 / org_h))
            self.tracker.init(img, bbox)

            return True


        def tracking(self, img):
            org_h, org_w, _ = img.shape
            cv2.putText(img, "Tracking", (100, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 0, 0), 2)
            img = cv2.resize(img, (320, 160))
            ok, bbox = self.tracker.update(img)
            if not ok:
                bbox = None
            if bbox is not None:
                bbox = (int(bbox[0] * org_w / 320), int(bbox[1] * org_h / 160), int(bbox[2] * org_w / 320), int(bbox[3] * org_h / 160))
                bbox = (int(bbox[0]), int(bbox[1]), int(bbox[0]+bbox[2]), int(bbox[1]+bbox[3]))

            return bbox