TRANSFORMERS DS VEHICLE UNLOCKER
================================
For Transformers: Autobots and Transformers: Decepticons (Nintendo DS)

This Python program applies the exact online-exclusive vehicle unlocks
and the bonus Jet flag. It handles either Save A or Save B (or both)
inside a 512-byte .sav file.

GRAPHICAL VERSION
-------------------------------------
1. Extract the ZIP and run Transformers_DS_Unlocker.py using Python.
   Alternatively, from a command prompt:
       py Transformers_DS_Unlocker.py
2. Click Browse and select your 512-byte AUTOBOTS.sav or DECEPTICONS.sav.
   The program detects the game and displays the Save A / Save B names.
3. Choose Save A, Save B, or Both.
4. Leave "Four online-exclusive vehicles" selected.
5. Leave "Bonus Jet" selected to also enable Skydive (Autobots) or
   G1 Starscream (Decepticons). Uncheck it to affect only online vehicles.
6. Click "Create unlocked copy..." and choose a NEW output filename.
   The program never overwrites any file or modifies the original.
7. Import the new .sav as Backup Memory in DeSmuME and reset the game.
   Test the unlock, save in-game, and restart to confirm it persists.

COMMAND LINE EXAMPLES
---------------------
Inspect the save, its two profiles, and checksum status:
    py Transformers_DS_Unlocker.py AUTOBOTS.sav --inspect

Autobots - unlock online vehicles + Skydive for Save A:
    py Transformers_DS_Unlocker.py AUTOBOTS.sav --slot A

Decepticons - unlock online vehicles + G1 Starscream for Save B:
    py Transformers_DS_Unlocker.py DECEPTICONS.sav --slot B

Unlock both profiles' online vehicles, but don't change the Jet flag:
    py Transformers_DS_Unlocker.py DECEPTICONS.sav --slot both --no-jet

Enable only the Jet, without changing the online vehicles:
    py Transformers_DS_Unlocker.py AUTOBOTS.sav --slot A --no-online

Choose your output filename:
    py Transformers_DS_Unlocker.py DECEPTICONS.sav --slot B -o MY_NEW_SAVE.sav

Use 'python' instead of 'py' on Linux/macOS where appropriate.

WHAT THE PROGRAM CHANGES
------------------------
* Detects Autobots signature 1A 74 03 00 or Decepticons 1B 74 03 00.
* For selected profile(s):
  - Enables the low 7 bits in the profile's 32-bit online reward field.
    Profile A: save offset 0x008; Profile B: save offset 0x00C.
  - Clears 4 online vehicle bits inside that profile's vehicle bitmap:
      record relative +0x6D, mask 0x03
      record relative +0x6E, mask 0x02
      record relative +0x70, mask 0x20
    Player record A starts at file offset 0x01C.
    Player record B starts at file offset 0x100.
* Optional bonus Jet: enables bit 0 in the shared 32-bit file header field
  at 0x004. THIS IS SHARED BY BOTH PROFILES, regardless of slot selection.
* Recalculates all three CRC-16/CCITT checksums:
    Player A: CRC over 0x01C..0x0FB, init 0x0000, stored at 0x0FC
    Player B: CRC over 0x100..0x1DF, init 0x0000, stored at 0x1E0
    Whole file: CRC over 0x000..0x1FD, init 0xBEEF, stored at 0x1FE
  All use polynomial 0x1021, stored little-endian.

