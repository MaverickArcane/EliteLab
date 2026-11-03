Option Explicit
Dim shell, files, root, python, cmd
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(root, "runtime\pythonw.exe")
If Not files.FileExists(python) Then
    MsgBox "The bundled Python runtime is missing. Extract the complete Windows bundle and try again.", 16, "EliteLab"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
cmd = Chr(34) & python & Chr(34) & " -m elitelab.desktop"
On Error Resume Next
shell.Run cmd, 0, False
If Err.Number <> 0 Then
    MsgBox "EliteLab could not start. Check that the extracted folder is accessible.", 16, "EliteLab"
    WScript.Quit 1
End If
