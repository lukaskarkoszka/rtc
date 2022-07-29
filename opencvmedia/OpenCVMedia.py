import asyncio
import fractions
import logging
import threading
import time
from typing import Optional, Set, Tuple
import av
from av import AudioFrame, VideoFrame

from aiortc.mediastreams import AUDIO_PTIME, MediaStreamError, MediaStreamTrack
from aiortc.contrib.media import PlayerStreamTrack, MediaPlayer

import cv2
import numpy as np

logger = logging.getLogger("media")

VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 1 / 30  # 30fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)

def opencv_player_worker(
    loop, audio_track, video_track, quit_event, throttle_playback
):
    audio_fifo = av.AudioFifo()
    audio_format_name = "s16"
    audio_layout_name = "stereo"
    audio_sample_rate = 48000
    audio_samples = 0
    audio_samples_per_frame = int(audio_sample_rate * AUDIO_PTIME)
    audio_resampler = av.AudioResampler(
        format=audio_format_name, layout=audio_layout_name, rate=audio_sample_rate
    )

    video_first_pts = None

    frame_time = None
    start_time = time.time()


    while not quit_event.is_set():
        try:
            frame = video_track.read()
            #frame = next(container.decode(*streams))
        except (av.AVError, StopIteration):
            if audio_track:
                asyncio.run_coroutine_threadsafe(audio_track._queue.put(None), loop)
            if video_track:
                asyncio.run_coroutine_threadsafe(video_track._queue.put(None), loop)
            break

        # read up to 1 second ahead
        if throttle_playback:
            elapsed_time = time.time() - start_time
            if frame_time and frame_time > elapsed_time + 1:
                time.sleep(0.1)

        if isinstance(frame, AudioFrame) and audio_track:
            if (
                frame.format.name != audio_format_name
                or frame.layout.name != audio_layout_name
                or frame.sample_rate != audio_sample_rate
            ):
                frame.pts = None
                frame = audio_resampler.resample(frame)

            # fix timestamps
            frame.pts = audio_samples
            frame.time_base = fractions.Fraction(1, audio_sample_rate)
            audio_samples += frame.samples

            audio_fifo.write(frame)
            while True:
                frame = audio_fifo.read(audio_samples_per_frame)
                if frame:
                    frame_time = frame.time
                    asyncio.run_coroutine_threadsafe(
                        audio_track._queue.put(frame), loop
                    )
                else:
                    break
        elif isinstance(frame, VideoFrame):
            if frame.pts is None:  # pragma: no cover
                logger.warning("Skipping video frame with no pts")
                continue

            # video from a webcam doesn't start at pts 0, cancel out offset
            if video_first_pts is None:
                video_first_pts = frame.pts
            frame.pts -= video_first_pts

            frame_time = frame.time
            asyncio.run_coroutine_threadsafe(video_track._queue.put(frame), loop)


class OpenCVPlayerStreamTrack(PlayerStreamTrack):
    def __init__(self, player, kind):
        super().__init__(player, kind)
        self.img = np.ones([480, 640, 3], dtype=np.uint8) * 200

    _start: float
    _timestamp: int

    def response(self):
        self.img = np.ones([480, 640, 3], dtype=np.uint8) * 100

    async def recv(self):
        if self.readyState != "live":
            raise MediaStreamError

        self._player._start(self)
        frame = await self._queue.get()
        if frame is None:
            self.stop()
            raise MediaStreamError
        frame_time = frame.time

        # control playback rate
        if (
                self._player is not None
                and self._player._throttle_playback
                and frame_time is not None
        ):
            if self._start is None:
                self._start = time.time() - frame_time
            else:
                wait = self._start + frame_time - time.time()
                await asyncio.sleep(wait)

        return frame

    def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
        if self.readyState != "live":
            raise MediaStreamError

        if hasattr(self, "_timestamp"):
            self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
            wait = self._start + (self._timestamp / VIDEO_CLOCK_RATE) - time.time()
            time.sleep(wait)
        else:
            self._start = time.time()
            self._timestamp = 0
        return self._timestamp, VIDEO_TIME_BASE

    def read(self) -> VideoFrame:
        pts, time_base = self.next_timestamp()

        # rotate image
        rows, cols, _ = self.img.shape
        M = cv2.getRotationMatrix2D((cols / 2, rows / 2), int(pts * time_base * 45), 1)
        img = cv2.warpAffine(self.img, M, (cols, rows))

        # create video frame
        frame = VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base

        return frame


class OpenCVMediaPlayer(MediaPlayer):
    """
    A media source that reads audio and/or video from a file.
    Examples:
    .. code-block:: python
        # Open a video file.
        player = MediaPlayer('/path/to/some.mp4')
        # Open an HTTP stream.
        player = MediaPlayer(
            'http://download.tsi.telecom-paristech.fr/'
            'gpac/dataset/dash/uhd/mux_sources/hevcds_720p30_2M.mp4')
        # Open webcam on Linux.
        player = MediaPlayer('/dev/video0', format='v4l2', options={
            'video_size': '640x480'
        })
        # Open webcam on OS X.
        player = MediaPlayer('default:none', format='avfoundation', options={
            'video_size': '640x480'
        })
    :param file: The path to a file, or a file-like object.
    :param format: The format to use, defaults to autodect.
    :param options: Additional options to pass to FFmpeg.
    """

    def __init__(self):
        #self.__container = av.open(file=file, format=format, mode="r", options=options)
        self.__thread: Optional[threading.Thread] = None
        self.__thread_quit: Optional[threading.Event] = None

        # examine streams
        self.__started: Set[OpenCVPlayerStreamTrack] = set()
        self.__streams = []
        self.__audio: Optional[OpenCVPlayerStreamTrack] = None
        #for stream in self.__container.streams:
        #    if stream.type == "audio" and not self.__audio:
        #        self.__audio = OpenCVPlayerStreamTrack(self, kind="audio")
        #        self.__streams.append(stream)
        #    elif stream.type == "video" and not self.__video:
        self.__video = OpenCVPlayerStreamTrack(self, kind="video")
        self.__streams.append(1)

        # check whether we need to throttle playback
        #container_format = set(self.__container.format.name.split(","))
        self._throttle_playback = False


        #asyncio.run_coroutine_threadsafe(self.__video.recv(), asyncio.get_event_loop())

    def videoResponse(self):
        self.__video.response()

    @property
    def audio(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains audio.
        """
        return self.__audio

    @property
    def video(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains video.
        """
        return self.__video

    def _start(self, track: OpenCVPlayerStreamTrack) -> None:
        self.__started.add(track)
        if self.__thread is None:
            #self.__log_debug("Starting worker thread")
            self.__thread_quit = threading.Event()
            self.__thread = threading.Thread(
                name="media-player",
                target=opencv_player_worker,
                args=(
                    asyncio.get_event_loop(),
                    #self.__container,
                    #self.__streams,
                    self.__audio,
                    self.__video,
                    self.__thread_quit,
                    self._throttle_playback,
                ),
            )
            self.__thread.start()

    def _stop(self, track: OpenCVPlayerStreamTrack) -> None:
        self.__started.discard(track)

        if not self.__started and self.__thread is not None:
            #self.__log_debug("Stopping worker thread")
            self.__thread_quit.set()
            self.__thread.join()
            self.__thread = None

        #if not self.__started and self.__container is not None:
        #    self.__container.close()
        #    self.__container = None

    #def __log_debug(self, msg: str, *args) -> None:
    #    logger.debug(f"player(%s) {msg}", self.__container.name, *args)
