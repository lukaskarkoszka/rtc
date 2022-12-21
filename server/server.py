import argparse
import asyncio
from asyncio import sleep
import json
import logging
import os
import ssl
import uuid
import time
import cv2
from aiohttp import web
from av import VideoFrame
from typing import Tuple
from objectDetection import objectDetection
import fractions
import threading

from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay

# BBOX = '[{"label":"person","bbox":[206,46,1264,727],"score":0.88}]'



class MediaStreamError(Exception):
    pass

class VideoTransformTrack(MediaStreamTrack):
    BBOX = None
    OLDBBOX = None
    CLICK = False
    ROOT = os.path.dirname(__file__)
    logger = logging.getLogger("pc")
    pcs = set()
    relay = MediaRelay()
    VIDEO_CLOCK_RATE = 90000
    VIDEO_PTIME = 1 / 30  # 30fps
    VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)

    tracker = cv2.TrackerCSRT_create()

    kind = "video"

    def __init__(self):
        super().__init__()  # don't forget this!

        video = cv2.VideoCapture(0)
        video.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        video.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.objectDetection = objectDetection()
        self.video = video

    async def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
        if self.readyState != "live":
            raise MediaStreamError

        if hasattr(self, "_timestamp"):
            self._timestamp += int(self.VIDEO_PTIME * self.VIDEO_CLOCK_RATE)
            wait = self._start + (self._timestamp / self.VIDEO_CLOCK_RATE) - time.time()
            await asyncio.sleep(wait)
        else:
            self._start = time.time()
            self._timestamp = 0
        return self._timestamp, self.VIDEO_TIME_BASE

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        res, img = self.video.read()


        if self.BBOX is not None:
            if self.CLICK:
                bbox = (int(self.BBOX[0]), int(self.BBOX[1]), int(self.BBOX[2]), int(self.BBOX[3]))
                self.ok = self.tracker.init(img, bbox)
                self.CLICK = False
            else:
                self.ok, bbox = self.tracker.update(img)
                if self.ok:
                    p1 = (int(bbox[0]), int(bbox[1]))
                    p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
                    cv2.rectangle(img, p1, p2, (255, 0, 0), 2, 1)
                    self.BBOX = bbox
                else:
                    cv2.putText(img, "Tracking failure detected", (100, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
                    self.BBOX = None
        else:
            img, detections = self.objectDetection.detection(img)
            self.BBOX = detections

        frame = VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

    async def index(self,request):
        content = open(os.path.join(self.ROOT, "index.html"), "r").read()
        return web.Response(content_type="text/html", text=content)


    async def javascript(self,request):
        content = open(os.path.join(self.ROOT, "client.js"), "r").read()
        return web.Response(content_type="application/javascript", text=content)

    async def css(self,request):
        content = open(os.path.join(self.ROOT, "styles.css"), "r").read()
        return web.Response(content_type="text/html", text=content)

    async def offer(self,request):
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        pc = RTCPeerConnection()
        pc_id = "PeerConnection(%s)" % uuid.uuid4()
        self.pcs.add(pc)

        def log_info(msg, *args):
            self.logger.info(pc_id + " " + msg, *args)

        log_info("Created for %s", request.remote)

        # prepare local media
        player = MediaPlayer(os.path.join(self.ROOT, "demo-instruct.wav"))
        if args.record_to:
            recorder = MediaRecorder(args.record_to)
        else:
            recorder = MediaBlackhole()

        @pc.on("datachannel")
        def on_datachannel(channel):
            print(channel.label, "with id", channel.id, "-", "created by remote party")
            if channel.label == "chat":
                @channel.on("message")
                def on_message(message):
                    log_info(str(message))
                    log_info("chat")
                    if isinstance(message, str):
                        try:
                            y = json.loads(message)
                            log_info(str(y))
                        except ValueError as e:
                            pass
            if channel.label == "joy":
                @channel.on("message")
                def on_message(message):
                    log_info(str(message))
                    log_info("joy")
                    if isinstance(message, str):
                        try:
                            y = json.loads(message)
                            log_info(str(y))
                        except ValueError as e:
                            pass

            if channel.label == "bbox":
                @channel.on("message")
                def on_message(message):
                    if self.BBOX != self.OLDBBOX:
                        if channel and self.BBOX is not None:
                            channel.send(str(self.BBOX))
                            self.OLDBBOX = self.BBOX

            if channel.label == "track":
                @channel.on("message")
                def on_message(message):
                    log_info(str(message))

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            log_info("Connection state is %s", pc.connectionState)
            if pc.connectionState == "failed":
                await pc.close()
                self.pcs.discard(pc)

        @pc.on("track")
        def on_track(track):
            log_info("Track %s received", track.kind)

            if track.kind == "audio":
                pc.addTrack(player.audio)
                recorder.addTrack(track)
            elif track.kind == "video":
                pc.addTrack(
                    VideoTransformTrack()
                )
                if args.record_to:
                    recorder.addTrack(self.relay.subscribe(track))

        # @pc.on('track')
        # def on_track(track):
        #     if track.kind == 'video':
        #         local_video = VideoTransformTrack()
        #         pc.addTrack(local_video)
        #     @pc.on('datachannel')
        #     def on_datachannel(channel):
        #         @channel.on('message')
        #         def on_message(message):
        #             channel.send(str(local_video))

            @track.on("ended")
            async def on_ended():
                log_info("Track %s ended", track.kind)
                await recorder.stop()

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        # # handle offer
        # await pc.setRemoteDescription(offer)
        # await recorder.start()
        #
        # # send answer
        # answer = await pc.createAnswer()
        # await pc.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
            ),
        )


    async def on_shutdown(self,app):
        # close peer connections
        coros = [pc.close() for pc in self.pcs]
        await asyncio.gather(*coros)
        self.pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # if args.cert_file:
    #     ssl_context = ssl.SSLContext()
    #     ssl_context.load_cert_chain(args.cert_file, args.key_file)
    # else:
    ssl_context = None
    vdt = VideoTransformTrack()

    app = web.Application()
    app.on_shutdown.append(vdt.on_shutdown)
    app.router.add_get("/", vdt.index)
    app.router.add_get("/client.js", vdt.javascript)
    app.router.add_get("/styles.css", vdt.css)
    app.router.add_post("/offer", vdt.offer)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=None
    )
