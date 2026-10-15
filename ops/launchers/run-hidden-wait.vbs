' Same trick as run-hidden.vbs, but WAITS for the child to exit.
' The task therefore stays "Running" for the real lifetime of the job, so
' MultipleInstances=IgnoreNew and ExecutionTimeLimit keep working. Without the
' wait, wscript returns instantly and the next slot would start a second copy
' while the first is still writing.
'
' SUPERSEDED 2026-10-15: this launcher used to hand its target straight to
' WScript.Shell.Run, which routes it through ShellExecute. For an unsigned
' .cmd the Attachment Manager then raises "Open File - Security Warning" and
' BLOCKS the job until a human clicks. Eight tasks went through this file, so
' every scheduled fire was waiting on somebody - a background job that was not
' background. Verified before the change: the dialog appeared and the job never
' ran. Executing cmd.exe instead asks the Attachment Manager about a signed,
' unzoned system binary; the .cmd becomes its argument. Verified after: no
' dialog, the job runs, and the exit code returns intact.
'
' The routing is conditional. A caller that passes something other than a
' .cmd/.bat keeps the previous behaviour unchanged, so this cannot break the
' shape where several arguments follow an executable.

Function IsCmdScript(ByVal p)
  Dim lower
  lower = LCase(p)
  IsCmdScript = (Right(lower, 4) = ".cmd") Or (Right(lower, 4) = ".bat")
End Function

Function QuoteArg(ByVal s)
  Dim t
  t = CStr(s)
  If Len(t) = 0 Then
    QuoteArg = """"""
    Exit Function
  End If
  If InStr(t, " ") > 0 Or InStr(t, vbTab) > 0 Or InStr(t, """") > 0 Then
    QuoteArg = """" & Replace(t, """", """""") & """"
  Else
    QuoteArg = t
  End If
End Function

If WScript.Arguments.Count < 1 Then
  WScript.Quit 1
End If

Dim target, i, line
target = WScript.Arguments.Item(0)

If IsCmdScript(target) Then
  ' cmd.exe /c "<script>" - the Attachment Manager inspects cmd.exe, not the
  ' script, so an unsigned .cmd no longer stops the job for a click.
  line = "cmd.exe /c " & QuoteArg(target)
Else
  line = QuoteArg(target)
End If

For i = 1 To WScript.Arguments.Count - 1
  line = line & " " & QuoteArg(WScript.Arguments.Item(i))
Next

' 0 = hidden window, True = wait for completion
CreateObject("WScript.Shell").Run line, 0, True
