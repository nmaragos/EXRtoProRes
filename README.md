# EXRtoProRes
Simple deadline submitter to convert an EXR sequence to ProRes movie

*Install:*\
  `\\DeadlineRepository10\custom\scripts\Submission\EXRtoProRes.py`\
  `\\DeadlineRepository10\custom\scripts\Jobs\EXRtoProRes.py`\
\
Creates an FFmpeg (Deadline FFmpeg plugin) job that encodes an EXR sequence to ProRes.
Output is written into the SAME source folder as `<firstFrameFilename>-ProRes.mov`

If a job is selected, defaults to job's output folder and picks that job's output sequence.
If selected job is not yet completed, submits ProRes job with dependency on it and informs the user.
Otherwise user can browse to any folder for an image sequnce to use.
