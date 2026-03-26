#!/usr/bin/env python3
from __future__ import absolute_import
from System import *
from System.Diagnostics import *
from System.IO import *

from Deadline.Plugins import DeadlinePlugin, PluginType
from Deadline.Scripting import *
from six.moves import range

def GetDeadlinePlugin():
    return FFmpegPlugin()

def CleanupDeadlinePlugin( deadlinePlugin ):
    deadlinePlugin.Cleanup()

class FFmpegPlugin(DeadlinePlugin):

    def __init__( self ):
        import sys
        if sys.version_info.major == 3:
            super().__init__()
        self.InitializeProcessCallback += self.InitializeProcess
        self.RenderExecutableCallback += self.RenderExecutable
        self.RenderArgumentCallback += self.RenderArgument
        self.PreRenderTasksCallback += self.PreRenderTasks
        self.PostRenderTasksCallback += self.PostRenderTasks
        self._frame_start = None
        self._frame_end = None
        self._frame_step = 1
        self._frame_total = None
        self._last_progress = -1

    def Cleanup(self):
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback

        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback
        del self.PreRenderTasksCallback
        del self.PostRenderTasksCallback

    def InitializeProcess(self):
        self.SingleFramesOnly=False
        self.StdoutHandling=True

        self.AddStdoutHandlerCallback(".*Error.*").HandleCallback += self.HandleStdoutError
        self.AddStdoutHandlerCallback(".*frame=\\s*(\\d+).*").HandleCallback += self.HandleStdoutFrame

    def RenderExecutable(self):
        return self.GetRenderExecutable("FFmpeg_RenderExecutable", "FFmpeg")


    def RenderArgument(self):
        outputFile = self.GetPluginInfoEntryWithDefault( "OutputFile", "" )
        outputFile = RepositoryUtils.CheckPathMapping( outputFile )
        outputFile = self.ProcessPath( outputFile )

        outputArgs = self.GetPluginInfoEntryWithDefault( "OutputArgs", "" )
        additionalArgs = self.GetPluginInfoEntryWithDefault( "AdditionalArgs", "" )
        useSameArgs = self.GetBooleanPluginInfoEntryWithDefault( "UseSameInputArgs", False )

        videoPreset = self.GetPluginInfoEntryWithDefault( "VideoPreset", "" )
        videoPreset = RepositoryUtils.CheckPathMapping( videoPreset )
        videoPreset = self.ProcessPath( videoPreset )

        audioPreset = self.GetPluginInfoEntryWithDefault( "AudioPreset", "" )
        audioPreset = RepositoryUtils.CheckPathMapping( audioPreset )
        audioPreset = self.ProcessPath( audioPreset )

        subtitlePreset = self.GetPluginInfoEntryWithDefault( "SubtitlePreset", "" )
        subtitlePreset = RepositoryUtils.CheckPathMapping( subtitlePreset )
        subtitlePreset = self.ProcessPath( subtitlePreset )

        if useSameArgs:
            inputArgs0 = self.GetPluginInfoEntryWithDefault( "InputArgs0", "" )

        if( outputFile == "" ):
            self.FailRender( "No output file was specified." )

        renderArgument = ""

        if useSameArgs:
            self.LogInfo( "UseSameInputArgs = True" )
        else:
            self.LogInfo( "UseSameInputArgs = False" )

        for i in range(0,9):
            inputFile = self.GetPluginInfoEntryWithDefault( "InputFile%d" % i, "" )
            inputArgs = self.GetPluginInfoEntryWithDefault( "InputArgs%d" % i, "" )
            replacePadding = self.GetBooleanPluginInfoEntryWithDefault( "ReplacePadding%d" % i, True )

            if inputFile != "":
                inputFile = RepositoryUtils.CheckPathMapping( inputFile )
                inputFile = self.ProcessPath( inputFile )

                # img-%03d
                if replacePadding:
                    currPadding = FrameUtils.GetFrameStringFromFilename( inputFile )
                    paddingSize = len( currPadding )

                    if '-' in currPadding:
                        front = "-%"
                        paddingSize = paddingSize - 1
                    else:
                        front = "%"

                    if paddingSize > 0:
                        padding = front + StringUtils.ToZeroPaddedString( paddingSize, 2, False ) + "d"
                        inputFile = FrameUtils.SubstituteFrameNumber( inputFile, padding )

                if (useSameArgs and inputArgs0 != ""):
                    renderArgument += "%s " % inputArgs0
                elif (not useSameArgs and inputArgs != ""):
                    renderArgument += "%s " % inputArgs

                renderArgument += "-i \"%s\" " % inputFile

        if outputArgs != "":
            renderArgument += "%s " % outputArgs

        renderArgument += "-y \"%s\"" % outputFile

        if additionalArgs != "":
            renderArgument += " %s" % additionalArgs

        if videoPreset != "":
            renderArgument += " -vpre \"%s\"" % videoPreset

        if audioPreset != "":
            renderArgument += " -apre \"%s\"" % audioPreset

        if subtitlePreset != "":
            renderArgument += " -spre \"%s\"" % subtitlePreset

        return renderArgument

    def ProcessPath( self, filepath ):
        if SystemUtils.IsRunningOnWindows():
            filepath = filepath.replace("/","\\")
            if filepath.startswith( "\\" ) and not filepath.startswith( "\\\\" ):
                filepath = "\\" + filepath
        else:
            filepath = filepath.replace("\\","/")
        return filepath

    def PreRenderTasks(self):
        self.LogInfo( "FFmpeg job starting..." )
        self._init_frame_progress()

    def PostRenderTasks(self):
        self.LogInfo( "FFmpeg job finished." )
        if self._frame_total:
            self.SetProgress(100)

    def HandleStdoutError(self):
        self.FailRender( self.GetRegexMatch(0) )

    def _init_frame_progress(self):
        start = self.GetIntegerPluginInfoEntryWithDefault("InputStartFrame0", 0)
        end = self.GetIntegerPluginInfoEntryWithDefault("InputEndFrame0", 0)
        step = self.GetIntegerPluginInfoEntryWithDefault("InputFrameStep0", 1)
        if step <= 0:
            step = 1
        if end < start:
            return
        total = ((end - start) // step) + 1
        if total <= 0:
            return
        self._frame_start = start
        self._frame_end = end
        self._frame_step = step
        self._frame_total = total
        self._last_progress = -1
        self.LogInfo(
            "FFmpeg progress enabled (start={0}, end={1}, step={2}, total={3})".format(
                start, end, step, total
            )
        )

    def HandleStdoutFrame(self):
        if not self._frame_total:
            self._init_frame_progress()
            if not self._frame_total:
                return
        try:
            frame = int(self.GetRegexMatch(1))
        except:
            return
        if frame < 0:
            frame = 0
        if frame >= self._frame_total:
            progress = 100
        else:
            progress = int((float(frame + 1) / float(self._frame_total)) * 100.0)
        if progress > self._last_progress:
            self._last_progress = progress
            self.SetProgress(progress)
            if self._frame_total:
                self.SetStatusMessage(
                    "Frame {0}/{1} ({2}%)".format(frame + 1, self._frame_total, progress)
                )
