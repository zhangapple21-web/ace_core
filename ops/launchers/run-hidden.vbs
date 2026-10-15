' Sibling of run-hidden-wait.vbs: launches hidden but does NOT wait.
' Used by four ACE tasks that pass powershell.exe with its own arguments.
'
' DO NOT add cmd.exe routing here. This launcher's first argument is a signed,
' unzoned executable (powershell.exe), so the Attachment Manager has nothing to
' ask about and no dialog appears. Wrapping its target in cmd.exe /c would
' mis-handle the arguments that follow it. The cmd.exe routing in
' run-hidden-wait.vbs exists for a different shape - a bare .cmd path - and
' must not be copied into this file.

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

Dim cmd, i
cmd = QuoteArg(WScript.Arguments.Item(0))
For i = 1 To WScript.Arguments.Count - 1
  cmd = cmd & " " & QuoteArg(WScript.Arguments.Item(i))
Next

CreateObject("WScript.Shell").Run cmd, 0, False
