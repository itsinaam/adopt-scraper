MailTesterNinjaApp – Email Validation Utility
=============================================

Powered by Unlimited & Limited

Introduction
------------
MailTesterNinjaApp is a professional tool designed to validate email addresses quickly and reliably using the MailTester Ninja API.

The application is available for Windows 10/11 and macOS. It is fully portable — no installation is required.

⚠️ Windows Security Notice
---------------------------
When running the application for the first time, Windows SmartScreen may display a warning message such as:

  "Windows protected your PC"

This happens because the application is unsigned. To proceed:

1. Right-click on `mailtesterninjaapp.exe`
2. Choose **Properties**
3. Check **Unblock** at the bottom if present
4. Click **OK**
5. Double-click the `.exe` to run

Alternatively, if using PowerShell, you may run:

    Unblock-File -Path .\mailtesterninjaapp.exe

This will prevent the warning on future runs.

⚠️ macOS Security Notice
-------------------------
On macOS, Gatekeeper may block the unsigned app on first launch
("cannot be opened because the developer cannot be verified").
To proceed:

1. Right-click (or Ctrl-click) the `mailtester` file and choose **Open**, then confirm **Open**.
2. Or, in Terminal, remove the quarantine flag:

    xattr -d com.apple.quarantine ./mailtester
    chmod +x ./mailtester
    ./mailtester

Usage Instructions
------------------

1. **Key Configuration**
   - Open the `key.txt` file located next to the executable.
   - Add your key like this:

        ```
        KEY=your_key_here
        ```

   - You can get your key for as low as 6.99 from:
     👉 https://mailtester.ninja/subscribe

2. **Preparing Email Input Files**
   - Create or drop your `.txt` or `.csv` files in the same folder as the executable.
   - Each file should contain a list of emails.
   - You can mix and match formats or content — the system is flexible and intelligent enough to detect and process what matters.
   - Files starting with the name `output` will be skipped automatically.

3. **Running the App**
   - Double-click `mailtesterninjaapp.exe`
   - The app will process all `.txt` and `.csv` files line by line
   - It will skip any line starting with `output`
   - Progress is displayed in the terminal with live updates and statistics

4. **Output**
   - For each input file, an output CSV will be generated containing the validation results.

Contact & Info
--------------
MailTesterNinjaApp is developed and maintained by **Unlimited & Limited**.

Learn more about the MailTester Ninja service:
🔗 https://mailtester.ninja/

Thank you for choosing MailTester Ninja!
