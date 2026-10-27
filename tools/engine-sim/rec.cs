// WASAPI loopback recorder: rec.exe <out.wav> <seconds>
// Captures what the default playback device is playing and writes 16-bit mono PCM at the mix rate.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MMDeviceEnumeratorCom { }

[ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
    [PreserveSig] int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
    [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}

[ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
    [PreserveSig] int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
}

[ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioClient {
    [PreserveSig] int Initialize(int shareMode, int streamFlags, long bufferDuration, long periodicity, IntPtr format, IntPtr sessionGuid);
    [PreserveSig] int GetBufferSize(out uint frames);
    [PreserveSig] int GetStreamLatency(out long latency);
    [PreserveSig] int GetCurrentPadding(out uint padding);
    [PreserveSig] int IsFormatSupported(int shareMode, IntPtr format, out IntPtr closest);
    [PreserveSig] int GetMixFormat(out IntPtr format);
    [PreserveSig] int GetDevicePeriod(out long def, out long min);
    [PreserveSig] int Start();
    [PreserveSig] int Stop();
    [PreserveSig] int Reset();
    [PreserveSig] int SetEventHandle(IntPtr handle);
    [PreserveSig] int GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
}

[ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioCaptureClient {
    [PreserveSig] int GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong devicePosition, out ulong qpcPosition);
    [PreserveSig] int ReleaseBuffer(uint frames);
    [PreserveSig] int GetNextPacketSize(out uint frames);
}

static class Rec {
    static void Check(int hr, string what) { if (hr < 0) throw new Exception(what + " failed: 0x" + hr.ToString("X8")); }

    static int Main(string[] args) {
        if (args.Length < 2) { Console.Error.WriteLine("usage: rec <out.wav> <seconds>"); return 2; }
        string path = args[0];
        double seconds = double.Parse(args[1], System.Globalization.CultureInfo.InvariantCulture);

        var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
        IMMDevice device;
        Check(enumerator.GetDefaultAudioEndpoint(0 /* eRender */, 1 /* eMultimedia */, out device), "GetDefaultAudioEndpoint");
        Guid iidClient = typeof(IAudioClient).GUID;
        object o;
        Check(device.Activate(ref iidClient, 23 /* CLSCTX_ALL */, IntPtr.Zero, out o), "Activate");
        var client = (IAudioClient)o;

        IntPtr fmt;
        Check(client.GetMixFormat(out fmt), "GetMixFormat");
        int channels = Marshal.ReadInt16(fmt, 2);
        int rate = Marshal.ReadInt32(fmt, 4);
        int blockAlign = Marshal.ReadInt16(fmt, 12);
        int bits = Marshal.ReadInt16(fmt, 14);
        int tag = Marshal.ReadInt16(fmt, 0) & 0xffff;
        bool isFloat = tag == 3 || (tag == 0xFFFE && bits == 32);
        Check(client.Initialize(0, 0x00020000 /* LOOPBACK */, 10000000, 0, fmt, IntPtr.Zero), "Initialize");

        Guid iidCapture = typeof(IAudioCaptureClient).GUID;
        Check(client.GetService(ref iidCapture, out o), "GetService");
        var capture = (IAudioCaptureClient)o;

        long wanted = (long)(seconds * rate), got = 0;
        var pcm = new MemoryStream();
        var w = new BinaryWriter(pcm);
        var frameBytes = new byte[0];
        Check(client.Start(), "Start");
        var started = DateTime.UtcNow;
        while (got < wanted) {
            Thread.Sleep(5);
            uint packet;
            Check(capture.GetNextPacketSize(out packet), "GetNextPacketSize");
            if (packet == 0) {
                // Loopback delivers nothing while the device is silent; pad so wall time still counts.
                if ((DateTime.UtcNow - started).TotalSeconds > seconds + 2) break;
                continue;
            }
            while (packet > 0) {
                IntPtr data; uint frames, flags; ulong dp, qp;
                Check(capture.GetBuffer(out data, out frames, out flags, out dp, out qp), "GetBuffer");
                int bytes = (int)frames * blockAlign;
                if (frameBytes.Length < bytes) frameBytes = new byte[bytes];
                bool silent = (flags & 2) != 0;
                if (!silent) Marshal.Copy(data, frameBytes, 0, bytes);
                for (int f = 0; f < frames && got < wanted; f++, got++) {
                    double sum = 0;
                    if (!silent) for (int c = 0; c < channels; c++) {
                        int off = f * blockAlign + c * (bits / 8);
                        sum += isFloat ? BitConverter.ToSingle(frameBytes, off) : BitConverter.ToInt16(frameBytes, off) / 32768.0;
                    }
                    double v = Math.Max(-1, Math.Min(1, sum / channels));
                    w.Write((short)Math.Round(v * 32767));
                }
                Check(capture.ReleaseBuffer(frames), "ReleaseBuffer");
                Check(capture.GetNextPacketSize(out packet), "GetNextPacketSize");
            }
        }
        client.Stop();

        byte[] body = pcm.ToArray();
        using (var f = new BinaryWriter(File.Create(path))) {
            f.Write(new[] { (byte)'R', (byte)'I', (byte)'F', (byte)'F' }); f.Write(36 + body.Length);
            f.Write(new[] { (byte)'W', (byte)'A', (byte)'V', (byte)'E', (byte)'f', (byte)'m', (byte)'t', (byte)' ' });
            f.Write(16); f.Write((short)1); f.Write((short)1); f.Write(rate); f.Write(rate * 2); f.Write((short)2); f.Write((short)16);
            f.Write(new[] { (byte)'d', (byte)'a', (byte)'t', (byte)'a' }); f.Write(body.Length); f.Write(body);
        }
        Console.WriteLine("wrote " + path + " " + rate + "Hz " + (got / (double)rate).ToString("0.00") + "s");
        return 0;
    }
}
