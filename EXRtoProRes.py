# EXRtoProRes.py
#
# Install:
#   \\DeadlineRepository10\custom\scripts\Submission\EXRtoProRes.py
#   \\DeadlineRepository10\custom\scripts\Jobs\EXRtoProRes.py
#
# Creates an FFmpeg (Deadline FFmpeg plugin) job that encodes an EXR sequence to ProRes.
# Output is written into the SAME source folder:
#   <firstFrameFilename>-ProRes.mov
#
# - If a job is selected, defaults to job's output folder and displays that folder.
# - Otherwise user can browse to a folder.
# - If selected job is not Completed, submits ProRes job with dependency on it and informs user.

from __future__ import print_function

import os
import profile
import re
from tkinter.constants import FALSE

from Deadline.Scripting import ClientUtils, MonitorUtils, PathUtils
from DeadlineUI.Controls.Scripting.DeadlineScriptDialog import DeadlineScriptDialog

from System.IO import Path, StreamWriter, Directory
from System.Text import Encoding
from System.Collections.Specialized import StringCollection

scriptDialog = None

_SEQ_RE = re.compile(r"^(?P<prefix>.*?)(?P<frame>\d+)(?P<suffix>\.[^.]+)$")
_DEFAULT_PROFILE_NAME = "ProRes 422 HQ"
_PRORES_PROFILE_SETTINGS = {
    "ProRes 422 Proxy": (0, "yuv422p10le"),
    "ProRes 422 LT": (1, "yuv422p10le"),
    "ProRes 422": (2, "yuv422p10le"),
    "ProRes 422 HQ": (3, "yuv422p10le"),
    "ProRes 4444": (4, "yuv444p10le"),
    "ProRes 4444 XQ": (5, "yuv444p10le"),
}

def _normpath(p):
    return os.path.normpath(p).replace("\\", "/")


def _first_nonempty_output_dir(job):
    try:
        dirs = list(job.JobOutputDirectories)
        for d in dirs:
            if d and d.strip():
                return d.strip()
    except:
        pass
    return ""


def _scan_exr_sequences(folder):
    if not folder or not Directory.Exists(folder):
        return []

    try:
        files = [f for f in Directory.GetFiles(folder) if f.lower().endswith(".exr")]
    except:
        return []

    groups = {}  # (prefix, suffix, padding) -> [(frame_int, fullpath), ...]
    for f in files:
        base = os.path.basename(f)
        m = _SEQ_RE.match(base)
        if not m:
            continue

        prefix = m.group("prefix")
        suffix = m.group("suffix")
        frame_str = m.group("frame")

        try:
            frame = int(frame_str)
        except:
            continue

        key = (prefix, suffix, len(frame_str))
        groups.setdefault(key, []).append((frame, f))

    candidates = []
    for (prefix, suffix, pad), items in groups.items():
        items.sort(key=lambda x: x[0])
        start_frame = items[0][0]
        end_frame = items[-1][0]
        first_file = items[0][1]
        candidates.append((first_file, start_frame, pad, len(items), end_frame))

    candidates.sort(key=lambda x: x[3], reverse=True)
    return candidates


def _detect_sequence(folder):
    cands = _scan_exr_sequences(folder)
    if not cands:
        return (None, None, None, None, None)
    first_file, start_frame, pad, count, end_frame = cands[0]
    return (first_file, start_frame, pad, end_frame, count)


def _make_output_mov_path(first_frame_file):
    folder = os.path.dirname(first_frame_file)
    base = os.path.basename(first_frame_file).partition('.')[0]
    return os.path.join(folder, base + "-ProRes.mov")

def _resolve_profile(profile_name, use_alpha):
    # profile_id, pxl_fmt = _PRORES_PROFILE_SETTINGS.get(
    #     profile_name, _PRORES_PROFILE_SETTINGS[_DEFAULT_PROFILE_NAME]
    # )
    profile_id, pxl_fmt = _PRORES_PROFILE_SETTINGS[profile_name]
    if use_alpha and pxl_fmt == "yuv444p10le":
        pxl_fmt = "yuva444p10le"
    return profile_id, pxl_fmt

def _build_ffmpeg_args(start_frame, fps, profile_name, use_alpha):
    input_args = "-start_number {0} -framerate {1}".format(int(start_frame), float(fps))
    # ProRes 422 HQ (profile 3), 10-bit 4:2:2
    ## output_args = "-c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le -movflags +faststart"
    # -stats forces ffmpeg to emit progress lines; -stats_period makes updates smoother.
    # output_args = "-stats -stats_period 0.2 -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le -movflags +faststart"
    profile_id, pxl_fmt = _resolve_profile(profile_name, use_alpha)
    output_args = f"-c:v prores_ks -profile:v {profile_id} -pix_fmt {pxl_fmt} -movflags +faststart"
    return input_args, output_args


def _submit_ffmpeg_job(source_folder, dependency_job_id, fps, profile_name, use_alpha):
    first_file, start_frame, pad, end_frame, frame_count = _detect_sequence(source_folder)
    if not first_file:
        return ("ERROR: No EXR sequence detected in: {0}".format(source_folder), None, None)

    if end_frame is None and frame_count:
        end_frame = start_frame + frame_count - 1

    output_mov = _make_output_mov_path(first_file)
    job_name = "ProRes - {0}".format(os.path.basename(first_file).partition('.')[0])

    input_args, output_args = _build_ffmpeg_args(start_frame, fps, profile_name, use_alpha)

    jobInfoFilename = Path.Combine(ClientUtils.GetDeadlineTempPath(), "prores_job_info.job")
    writer = StreamWriter(jobInfoFilename, False, Encoding.Unicode)
    writer.WriteLine("Plugin=FFmpeg")
    writer.WriteLine("Name={0}".format(job_name))
    writer.WriteLine("Frames=0")
    writer.WriteLine("ChunkSize=1")
    writer.WriteLine("OutputFilename0={0}".format(_normpath(output_mov)))
    if dependency_job_id:
        writer.WriteLine("JobDependencies={0}".format(dependency_job_id))
    writer.Close()

    pluginInfoFilename = Path.Combine(ClientUtils.GetDeadlineTempPath(), "prores_plugin_info.job")
    writer = StreamWriter(pluginInfoFilename, False, Encoding.Unicode)

    writer.WriteLine("InputFile0={0}".format(_normpath(first_file)))
    writer.WriteLine("InputArgs0={0}".format(input_args))
    writer.WriteLine("ReplacePadding0=True")
    writer.WriteLine("InputStartFrame0={0}".format(int(start_frame)))
    writer.WriteLine("InputEndFrame0={0}".format(int(end_frame)))
    # writer.WriteLine("InputFrameStep0=1")
    writer.WriteLine("InputPaddingSize0={0}".format(int(pad) if pad else 0))

    writer.WriteLine("OutputFile={0}".format(_normpath(output_mov)))
    writer.WriteLine("OutputArgs={0}".format(output_args))

    writer.Close()

    args = StringCollection()
    args.Add(jobInfoFilename)
    args.Add(pluginInfoFilename)

    results = ClientUtils.ExecuteCommandAndGetOutput(args)
    return (results, output_mov, job_name)


def __main__():
    global scriptDialog

    scriptDialog = DeadlineScriptDialog()
    scriptDialog.SetTitle("Create ProRes from EXR Sequence")

    # Selected jobs (if invoked from Job right-click, this will typically be populated)
    try:
        selected_jobs = list(MonitorUtils.GetSelectedJobs())
    except:
        selected_jobs = []

    default_job = selected_jobs[0] if len(selected_jobs) == 1 else None
    default_job_folder = _first_nonempty_output_dir(default_job) if default_job else ""
    useSelectedDefault = True if (default_job and default_job_folder) else False

    scriptDialog.AddGrid()

    # scriptDialog.AddControlToGrid(
    #     "InfoLabel",
    #     "LabelControl",
    #     "Pick a folder with an EXR sequence, or use the selected job's output folder.",
    #     0, 0, "", True, 1, 3
    # )

    scriptDialog.AddControlToGrid(
        "SourceSeparator", "SeparatorControl", "EXR sequence source", 0, 0, colSpan=3
    )

    # AddSelectionControlToGrid(name, control, value, theFilter, row, column, tooltip, expand, rowSpan, colSpan, browserLocation)
    useSelectedCtrl = scriptDialog.AddSelectionControlToGrid(
        "UseSelectedBox",
        "CheckBoxControl",
        useSelectedDefault,
        "Use selected job's output folder",
        1, 0, "", True, 1, 3, ""
    )

    scriptDialog.AddControlToGrid("SelFolderLabel", "LabelControl", "Selected Job's Folder", 2, 0, "", True, 1, 1)

    scriptDialog.AddControlToGrid(
        "SelFolderBox",
        "ReadOnlyTextControl",
        default_job_folder,
        2, 1, "", True, 1, 2
    )

    scriptDialog.AddControlToGrid("FolderLabel", "LabelControl", "EXR Folder", 3, 0, "", True, 1, 1)

    folderCtrl = scriptDialog.AddSelectionControlToGrid(
        "FolderBox",
        "FolderBrowserControl",
        "",
        "",         # theFilter (ignored for folder browser)
        3, 1,
        "", True, 1, 2, ""
    )

    scriptDialog.AddControlToGrid(
        "ProResSeparator", "SeparatorControl", "ProRes options", 4, 0, colSpan=3
    )

    scriptDialog.AddControlToGrid("ProfileLabel", "LabelControl", "ProRes Profile", 5, 0, "", True, 1, 1)
    profileCtrl = scriptDialog.AddComboControlToGrid("ProfileCombo", "ComboControl", "ProRes 422 HQ",
        ["ProRes 422 Proxy", "ProRes 422 LT","ProRes 422", "ProRes 422 HQ", "ProRes 4444", "ProRes 4444 XQ"],
        5, 1, "Select the ffmpeg ProRes profile", False, 1, 3
    )
    # scriptDialog.AddControlToGrid("emptyLabel", "LabelControl", "", 4, 2, "", True, 1, 1)

    useAlpha = scriptDialog.AddSelectionControlToGrid(
        "UseAlphaChannel",
        "CheckBoxControl",
        True,
        "Include Alpha channel",
        6, 1
    )

    scriptDialog.AddControlToGrid("FpsLabel", "LabelControl", "FPS", 7, 0, "", True, 1, 1)
    fpsCtrl = scriptDialog.AddControlToGrid("FpsBox", "TextControl", "24", 7, 1, "", True, 1, 1)
    scriptDialog.AddControlToGrid("FpsHint", "LabelControl", "(e.g. 24 / 25 / 30)", 7, 2, "", True, 1, 1)

    scriptDialog.EndGrid()

    scriptDialog.AddGrid()
    scriptDialog.AddHorizontalSpacerToGrid("HSpacer", 0, 0)
    submitBtn = scriptDialog.AddControlToGrid("SubmitButton", "ButtonControl", "Submit", 1, 1, "", False, 1, 1)
    closeBtn = scriptDialog.AddControlToGrid("CloseButton", "ButtonControl", "Close", 1, 2, "", False, 1, 1)
    scriptDialog.EndGrid()

    def _sync_enabled(*args):
        useSelected = bool(scriptDialog.GetValue("UseSelectedBox"))
        profile_name = scriptDialog.GetValue("ProfileCombo")
        use_alpha = bool(scriptDialog.GetValue("UseAlphaChannel"))

        if useSelected:
            # Update displayed selected-job folder (best-effort)
            try:
                cur_sel = list(MonitorUtils.GetSelectedJobs())
            except:
                cur_sel = []

            if len(cur_sel) == 1:
                folder = _first_nonempty_output_dir(cur_sel[0])
            else:
                folder = ""
            scriptDialog.SetValue("SelFolderBox", folder)

        # Show selected folder controls only when checkbox is on
        scriptDialog.SetEnabled("SelFolderLabel", useSelected)
        scriptDialog.SetEnabled("SelFolderBox", useSelected)

        # Manual folder picker enabled only when checkbox is off
        scriptDialog.SetEnabled("FolderLabel", not useSelected)
        scriptDialog.SetEnabled("FolderBox", not useSelected)

    def _update_alpha_enabled(*args):
        profile_name = scriptDialog.GetValue("ProfileCombo")
        _, pxl_fmt = _resolve_profile(profile_name, False)
        supports_alpha = (pxl_fmt == "yuv444p10le")

        if not supports_alpha:
            scriptDialog.SetValue("UseAlphaChannel", False)

        scriptDialog.SetEnabled("UseAlphaChannel", supports_alpha)

    def _on_close(*args):
        scriptDialog.closeEvent(None)

    def _on_submit(*args):
        fps_str = (scriptDialog.GetValue("FpsBox") or "").strip()
        try:
            fps = float(fps_str)
            if fps <= 0:
                raise ValueError()
        except:
            scriptDialog.ShowMessageBox("Invalid FPS: {0}".format(fps_str), "Error")
            return

        profile_name = scriptDialog.GetValue("ProfileCombo")
        use_alpha = bool(scriptDialog.GetValue("UseAlphaChannel"))

        useSelected = bool(scriptDialog.GetValue("UseSelectedBox"))

        if useSelected:
            try:
                cur_sel = list(MonitorUtils.GetSelectedJobs())
            except:
                cur_sel = []

            if len(cur_sel) != 1:
                scriptDialog.ShowMessageBox(
                    "Please select exactly ONE job (currently selected: {0}).".format(len(cur_sel)),
                    "Error"
                )
                return

            job = cur_sel[0]
            folder = _first_nonempty_output_dir(job)
            if not folder:
                scriptDialog.ShowMessageBox(
                    "Selected job '{0}' has no output directory set.".format(job.JobName),
                    "Error"
                )
                return

            dep_id = None
            try:
                status_str = str(job.JobStatus)
                if "Completed" not in status_str:
                    dep_id = job.JobId
            except:
                pass

            local_warning = PathUtils.IsPathLocal(folder)
            res, out_mov, _job_name = _submit_ffmpeg_job(folder, dep_id, fps, profile_name, use_alpha)

            msg = "Source job: {0}\nSource folder: {1}\nOutput: {2}\n\nResult:\n{3}".format(
                job.JobName,
                folder,
                out_mov if out_mov else "(none)",
                res
            )

            if dep_id:
                msg = (
                    "NOTE: Source job is not Completed; the ProRes job was submitted with a dependency.\n\n"
                    + msg
                )
            if local_warning:
                msg = (
                    "WARNING: Source path appears to be local. Deadline Workers may not be able to access it.\n\n"
                    + msg
                )

            scriptDialog.ShowMessageBox(msg, "Submission Results")
            return

        # Manual folder
        folder = (scriptDialog.GetValue("FolderBox") or "").strip()
        if not folder:
            scriptDialog.ShowMessageBox("Please select an EXR folder.", "Error")
            return

        local_warning = PathUtils.IsPathLocal(folder)
        res, out_mov, _job_name = _submit_ffmpeg_job(folder, None, fps, profile_name, use_alpha)

        msg = "Source folder: {0}\nOutput: {1}\n\nResult:\n{2}".format(
            folder,
            out_mov if out_mov else "(none)",
            res
        )

        if local_warning:
            msg = (
                "WARNING: Source path appears to be local. Deadline Workers may not be able to access it.\n\n"
                + msg
            )

        scriptDialog.ShowMessageBox(msg, "Submission Results")

    # Wire events (no dialog-wide ValueModified exists)
    submitBtn.ValueModified.connect(_on_submit)
    closeBtn.ValueModified.connect(_on_close)

    useSelectedCtrl.ValueModified.connect(_sync_enabled)
    # Optional: keep UI consistent if user edits fields
    folderCtrl.ValueModified.connect(_sync_enabled)
    fpsCtrl.ValueModified.connect(_sync_enabled)
    profileCtrl.ValueModified.connect(_update_alpha_enabled)

    _sync_enabled()
    _update_alpha_enabled()
    scriptDialog.ShowDialog(False)
