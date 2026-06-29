# Binary Sense 分析报告

**分析时间**: 2026-06-29T19:49:39.202424
**目标文件**: BlueStacksMicroInstaller.exe
**文件大小**: 812.4 KB (831864 bytes)

## 1. 基本信息

| 属性 | 值 |
|------|-----|
| MD5 | `08ea1c9bd30a1caf30faee7994555006` |
| SHA1 | `7fe4d0543a3550104c1347442f0198939524b57e` |
| SHA256 | `ad3e08a06944733fd0ccf39b7af64b9ab6412367d22dd073016e581f3ca945c2` |
| 文件类型 | PE32 (32位) |

## 2. PE 头部信息

- **Machine**: i386 (x86)
- **节区数量**: 4
- **时间戳**: 2021-07-19T21:21:27
- **子系统**: WINDOWS_GUI
- **入口点**: 0x0001A5B2
- **镜像基址**: 0x00400000
- **镜像大小**: 319488 bytes
- **文件对齐**: 512
- **节区对齐**: 4096
- **OS 版本**: 5.0
- **特性标志**: EXECUTABLE_IMAGE, 32BIT_MACHINE, RELOCS_STRIPPED

## 3. 节区表

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 原始偏移 | 特性 |
|------|----------|----------|----------|----------|------|
| .text | 0x00001000 | 133226 | 133632 | 0x00000400 | CODE, EXECUTE, READ |
| .rdata | 0x00022000 | 30512 | 30720 | 0x00020E00 | INITIALIZED_DATA, READ |
| .data | 0x0002A000 | 17988 | 6144 | 0x00028600 | INITIALIZED_DATA, READ, WRITE |
| .rsrc | 0x0002F000 | 122968 | 123392 | 0x00029E00 | INITIALIZED_DATA, READ |

## 4. 导入表 (4 个DLL, 120 个函数)

### KERNEL32.dll (100 个函数)

**按名称导入**:

```
  DeleteCriticalSection
  EnterCriticalSection
  LeaveCriticalSection
  GetLastError
  MultiByteToWideChar
  WideCharToMultiByte
  LoadLibraryExW
  GetModuleFileNameW
  LocalFree
  FormatMessageW
  GetSystemDirectoryW
  CloseHandle
  SetFileTime
  CreateFileW
  SetFileAttributesW
  RemoveDirectoryW
  GetProcAddress
  GetModuleHandleW
  CreateDirectoryW
  DeleteFileW
  ... 还有 30 个
```

### USER32.dll (16 个函数)

**按名称导入**:

```
  DestroyWindow
  LoadIconW
  EndDialog
  KillTimer
  SetTimer
  SetWindowTextW
  PostMessageW
  SendMessageW
  MessageBoxW
  DialogBoxParamW
  GetWindowLongW
  SetWindowLongW
  ShowWindow
  LoadStringW
  CharUpperW
  GetDlgItem
```

### SHELL32.dll (1 个函数)

**按名称导入**:

```
  ShellExecuteExW
```

### OLEAUT32.dll (3 个函数)

**按序号导入**: 3 个

## 5. 壳/保护检测

- 未检测到已知壳特征

## 6. 开发框架/语言检测

- **Visual Basic** (置信度: 50%)
  - String: `vector vbase copy constructor iterator'

## 7. 字符串样本 (共约 300 个)

| 偏移 | 长度 | 字符串 |
|------|------|--------|
| 0x0000004D | 40 | !This program cannot be run in DOS mode. |
| 0x0000020F | 7 | `.rdata |
| 0x00000237 | 6 | @.data |
| 0x000011F4 | 7 | M Qhx1B |
| 0x0000129C | 7 | M0QhX1B |
| 0x00001B41 | 6 | EH9}Hu |
| 0x00001B9E | 7 | M@9U@w  |
| 0x00001D1A | 7 | E ;EHrS |
| 0x00001DCA | 6 | @;EHs# |
| 0x00001DFD | 6 | E$9ELs |
| 0x00002736 | 6 | t9IIt* |
| 0x000045F4 | 6 | u\8];t |
| 0x000046F7 | 7 | u[9}huV |
| 0x00004777 | 7 | uA9}hu< |
| 0x00004900 | 7 | MX9Mpv^ |
| 0x0000495E | 6 | MX;Mpr |
| 0x00004A4D | 8 | }49}TrBw |
| 0x00004A73 | 6 | E4;ETr |
| 0x00004A7D | 6 | EP9E0r |
| 0x00005331 | 6 | ^`9^tv |
| 0x0000706D | 11 | ^49^,u h,.B |
| 0x000071E0 | 7 | u=9^<t8 |
| 0x0000770E | 7 | t)Ht"Ht |
| 0x00007757 | 8 | NX;NTt&P |
| 0x000079A2 | 6 | Nt;Npu |
| 0x0000BFFD | 6 | V`8^=t |
| 0x0000C04F | 6 | u39^`u |
| 0x0000C18E | 6 | F<;FDr |
| 0x0000C1A5 | 7 | FD;F<uV |
| 0x0000C36F | 6 | FH;FPu |
| ... | ... | 还有 70 个字符串 |

## 8. 分析发现

### [file_type] File type detected: PE
- 置信度: 95%
- 发现时间: 2026-06-29T19:49:39.171580

### [pe_structure] PE structure: 32-bit, 4 sections
- 置信度: 95%
- 发现时间: 2026-06-29T19:49:39.201422

### [sections] Found 4 sections
- 置信度: 99%
- 发现时间: 2026-06-29T19:49:39.202424

### [imports] Import table: 4 DLLs, 120 functions
- 置信度: 95%
- 发现时间: 2026-06-29T19:49:39.202424

### [framework] Most likely framework: Visual Basic
- 置信度: 60%
- 发现时间: 2026-06-29T19:49:39.202424

### [strings] Extracted ~300 printable strings
- 置信度: 90%
- 发现时间: 2026-06-29T19:49:39.202424

---

*报告由 Binary Sense 自动生成*