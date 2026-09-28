/*
    This file is part of tdm-launcher.
    Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
    Miniature Mobile Robots group, Switzerland
    Author: Yves Piguet
*/

using System;
using System.Windows.Forms;
using System.Diagnostics;
using System.ComponentModel;
using System.Threading;
using System.IO;

public class MainForm: System.Windows.Forms.Form
{
    private System.Windows.Forms.NotifyIcon notifyIcon;
    private System.ComponentModel.IContainer components;

	private Process process;

    [STAThread]
    static int Main(string[] args)
    {
		if (args.Length == 1 && args[0] == "--check-backend")
			return CheckBackend();
		if (args.Length != 0)
			return 2;
		using (var singleApp = new Mutex(false, "org.mobsya.thymio-2-device-manager"))
			if (singleApp.WaitOne(TimeSpan.Zero))
				Application.Run(new MainForm());
		return 0;
    }

    private static ProcessStartInfo BackendStartInfo()
    {
        return new ProcessStartInfo {
            FileName = Path.Combine(AppContext.BaseDirectory, TDMLauncher.Properties.Resources.TDMPath),
            WorkingDirectory = AppContext.BaseDirectory,
            UseShellExecute = false,
            WindowStyle = ProcessWindowStyle.Hidden,
            CreateNoWindow = true
        };
    }

    // A diagnostic command also exercises backend discovery after single-file extraction.
    private static int CheckBackend()
    {
        try {
            var info = BackendStartInfo();
            info.ArgumentList.Add("--help");
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            using (var backend = Process.Start(info)) {
                var stdout = backend.StandardOutput.ReadToEndAsync();
                var stderr = backend.StandardError.ReadToEndAsync();
                if (!backend.WaitForExit(15000)) {
                    backend.Kill(true);
                    backend.WaitForExit();
                    Console.Error.WriteLine("Backend help command timed out.");
                    return 1;
                }
                string output = stdout.GetAwaiter().GetResult() + stderr.GetAwaiter().GetResult();
                Console.Write(output);
                // TDM intentionally exits with status 1 for --help.
                return backend.ExitCode == 1 && output.Contains("--help") ? 0 : 1;
            }
        } catch (Exception error) {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
    }

	public MainForm()
    {
		System.Windows.Forms.ContextMenuStrip contextMenu = new System.Windows.Forms.ContextMenuStrip();
		System.Windows.Forms.ToolStripMenuItem menuItemExit = new System.Windows.Forms.ToolStripMenuItem();

        menuItemExit.Text = "E&xit";
        menuItemExit.Click += new System.EventHandler(this.Exit);
        contextMenu.Items.Add(menuItemExit);

		// window title, in case it appears somewhere (window itself is hidden by OnLoad)
		this.Text = TDMLauncher.Properties.Resources.TDMName;

		this.components = new System.ComponentModel.Container();
		notifyIcon = new System.Windows.Forms.NotifyIcon(this.components);

		notifyIcon.Icon = TDMLauncher.Properties.Resources.Thymio;
		notifyIcon.ContextMenuStrip = contextMenu;
		notifyIcon.Text = TDMLauncher.Properties.Resources.TDMName;
		notifyIcon.Visible = true;
	}

	private void LaunchTDM()
	{
		ProcessStartInfo info = BackendStartInfo();

		try
		{
			this.process = Process.Start(info);
		}
		catch (System.ComponentModel.Win32Exception)
		{
			// failure: change icon
			notifyIcon.Icon = TDMLauncher.Properties.Resources.Thymio_crossed;
		}
	}

	protected override void OnLoad(EventArgs e)
	{
		Visible = false;
		ShowInTaskbar = false;
		base.OnLoad(e);

		LaunchTDM();
	}

	protected override void Dispose(bool disposing)
	{
		if (disposing && components != null)
			components.Dispose();

		base.Dispose(disposing);
	}

	private void Exit(object Sender, EventArgs e)
	{
		if (this.process != null)
		{
			// should send a gentle shutdown request message via tcp instead of killing
			try
			{
				this.process.Kill();
				this.process.WaitForExit();
			}
			catch (InvalidOperationException)
			{
				// ignore, process was already terminated
			}
		}

		// exit
		this.Close();
	}
}
