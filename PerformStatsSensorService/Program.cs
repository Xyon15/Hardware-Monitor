using LibreHardwareMonitor.Hardware;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Linq;
using System.Collections.Generic;

var builder = WebApplication.CreateBuilder(args);

// Run as Windows Service when installed
builder.Host.UseWindowsService();

// Kestrel binding to loopback only for security
builder.WebHost.ConfigureKestrel(options =>
{
    options.ListenLocalhost(9755); // http://127.0.0.1:9755
});

// Add logging (defaults are fine; levels controlled by environment if needed)
// builder.Logging.SetMinimumLevel(LogLevel.Information);

builder.Services.AddSingleton<SensorReader>();

var app = builder.Build();

app.MapGet("/metrics", (SensorReader reader) =>
{
    // Return last cached or freshly read data with internal try/catch
    var data = reader.ReadSafe();
    return Results.Text(JsonSerializer.Serialize(data), "application/json");
});

// Diagnostic endpoint: list all hardware and sensors with current values
app.MapGet("/sensors", (SensorReader reader) =>
{
    var data = reader.SensorsDump();
    return Results.Text(JsonSerializer.Serialize(data, new JsonSerializerOptions { WriteIndented = true }), "application/json");
});

// Health endpoint
app.MapGet("/healthz", (SensorReader reader) =>
{
    var healthy = reader.IsHealthy();
    return Results.Text(JsonSerializer.Serialize(new { status = healthy ? "ok" : "degraded" }), "application/json");
});

app.Run();

public sealed class SensorReader : IDisposable
{
    private readonly Computer _comp;
    private readonly ILogger<SensorReader> _logger;

    private RootMetrics _lastData = new RootMetrics();
    private DateTime _lastRead = DateTime.MinValue;
    private readonly TimeSpan _minInterval = TimeSpan.FromMilliseconds(500);

    public SensorReader(ILogger<SensorReader> logger)
    {
        _logger = logger;
        _comp = new Computer
        {
            IsCpuEnabled = true,
            IsGpuEnabled = true, // optional GPU from LHM
            IsMemoryEnabled = true,
            IsStorageEnabled = false,
            IsMotherboardEnabled = true, // enable motherboard (Super I/O) sensors for CPU temps
            IsNetworkEnabled = false
        };
        _comp.Open();
    }

    public RootMetrics ReadSafe()
    {
        var now = DateTime.UtcNow;
        if (now - _lastRead < _minInterval)
        {
            return _lastData;
        }

        try
        {
            var fresh = ReadInternal();
            _lastData = fresh;
            _lastRead = now;
            return fresh;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "ReadInternal failed; returning cached data");
            return _lastData;
        }
    }

    private RootMetrics ReadInternal()
    {
        _comp.Accept(new UpdateVisitor());

        double? cpuTemp = null;
        double? cpuLoad = null;
        double? ramUsedPct = null;
        double? ramUsedGb = null;
        double? ramTotalGb = null;
        double? ramAvailGb = null;
        double? gpuLoad = null;
        double? gpuTemp = null;
        double? vramUsedPct = null;
        double? vramUsedGb = null;
        double? vramTotalGb = null;
        string? gpuModel = null;

        foreach (var hw in _comp.Hardware)
        {
            if (hw.HardwareType == HardwareType.Cpu)
            {
                // Include CPU sub-hardware sensors as some CPUs expose temps there
                IEnumerable<ISensor> cpuSensors = hw.Sensors.Concat(hw.SubHardware.SelectMany(sh => sh.Sensors));

                // Collect all temperature readings to decide a robust fallback
                var allCpuTemps = new List<(string name, double value)>();

                foreach (var sensor in cpuSensors)
                {
                    var sname = sensor.Name ?? string.Empty;
                    if (sensor.SensorType == SensorType.Temperature)
                    {
                        if (sensor.Value.HasValue)
                        {
                            allCpuTemps.Add((sname, sensor.Value.Value));
                        }

                        // Prefer Package/Die/Tctl first
                        if (sname.Contains("Package", StringComparison.OrdinalIgnoreCase)
                            || sname.Contains("Tctl", StringComparison.OrdinalIgnoreCase)
                            || sname.Contains("Tdie", StringComparison.OrdinalIgnoreCase)
                            || sname.Contains("Die", StringComparison.OrdinalIgnoreCase))
                        {
                            cpuTemp ??= sensor.Value;
                        }

                        // Next preference: names starting with CPU or containing Core Average
                        if (cpuTemp == null && (sname.StartsWith("CPU", StringComparison.OrdinalIgnoreCase)
                                                || sname.Contains("Core Average", StringComparison.OrdinalIgnoreCase)))
                        {
                            cpuTemp ??= sensor.Value;
                        }

                        // Generic fallback capture (first available)
                        cpuTemp ??= sensor.Value;
                    }

                    if (sensor.SensorType == SensorType.Load && sname.Equals("CPU Total", StringComparison.OrdinalIgnoreCase))
                        cpuLoad ??= sensor.Value;
                }

                // Final fallback: if cpuTemp still null but we collected temps, take the max (hotter point)
                if (cpuTemp == null && allCpuTemps.Count > 0)
                {
                    cpuTemp = allCpuTemps.Max(t => (double?)t.value);
                }
            }
            else if (hw.HardwareType == HardwareType.Memory)
            {
                foreach (var sensor in hw.Sensors)
                {
                    if (sensor.SensorType == SensorType.Load && sensor.Name.Equals("Memory", StringComparison.OrdinalIgnoreCase))
                        ramUsedPct ??= sensor.Value;
                    if (sensor.SensorType == SensorType.Data)
                    {
                        var name = sensor.Name ?? string.Empty;
                        if (name.Contains("Used", StringComparison.OrdinalIgnoreCase) && name.Contains("Memory", StringComparison.OrdinalIgnoreCase))
                            ramUsedGb ??= sensor.Value;
                        if (name.Contains("Available", StringComparison.OrdinalIgnoreCase) && name.Contains("Memory", StringComparison.OrdinalIgnoreCase))
                            ramAvailGb ??= sensor.Value;
                        if (name.Contains("Total", StringComparison.OrdinalIgnoreCase) && name.Contains("Memory", StringComparison.OrdinalIgnoreCase))
                            ramTotalGb ??= sensor.Value;
                    }
                }
            }
            else if (hw.HardwareType == HardwareType.Motherboard)
            {
                // Some systems expose CPU temps via Super I/O under Motherboard
                IEnumerable<ISensor> mbSensors = hw.Sensors.Concat(hw.SubHardware.SelectMany(sh => sh.Sensors));
                var allCpuTempsMb = new List<double>();
                foreach (var sensor in mbSensors)
                {
                    if (sensor.SensorType == SensorType.Temperature)
                    {
                        var n = sensor.Name ?? string.Empty;
                        bool looksCpu = n.Contains("CPU", StringComparison.OrdinalIgnoreCase)
                                        || n.Contains("Package", StringComparison.OrdinalIgnoreCase)
                                        || n.Contains("Tctl", StringComparison.OrdinalIgnoreCase)
                                        || n.Contains("Tdie", StringComparison.OrdinalIgnoreCase)
                                        || n.Contains("Die", StringComparison.OrdinalIgnoreCase);
                        if (looksCpu)
                        {
                            if (cpuTemp == null && sensor.Value.HasValue)
                                cpuTemp = sensor.Value;
                            if (sensor.Value.HasValue)
                                allCpuTempsMb.Add(sensor.Value.Value);
                        }
                    }
                }
                if (cpuTemp == null && allCpuTempsMb.Count > 0)
                    cpuTemp = allCpuTempsMb.Max();
            }
            else if (hw.HardwareType == HardwareType.GpuNvidia || hw.HardwareType == HardwareType.GpuAmd || hw.HardwareType == HardwareType.GpuIntel)
            {
                // Update sensors for this hardware and its sub-hardware to ensure latest readings
                hw.Update();
                foreach (var sub in hw.SubHardware) sub.Update();

                gpuModel ??= hw.Name;

                // Collect sensors including sub-hardware
                IEnumerable<ISensor> allSensors = hw.Sensors
                    .Concat(hw.SubHardware.SelectMany(sh => sh.Sensors));

                foreach (var sensor in allSensors)
                {
                    var name = sensor.Name ?? string.Empty;

                    // Debug (under logger only)
                    _logger.LogDebug("GPU Sensor: {Name} ({Type}) = {Value}", name, sensor.SensorType, sensor.Value);

                    // GPU Load candidates: Core/Graphics/3D/Total
                    if (sensor.SensorType == SensorType.Load &&
                        (name.Contains("Core", StringComparison.OrdinalIgnoreCase)
                         || name.Contains("Graphics", StringComparison.OrdinalIgnoreCase)
                         || name.Contains("3D", StringComparison.OrdinalIgnoreCase)
                         || name.Contains("GPU", StringComparison.OrdinalIgnoreCase)
                         || name.Contains("Total", StringComparison.OrdinalIgnoreCase)))
                    {
                        gpuLoad ??= sensor.Value;
                    }

                    // GPU Temperature candidates (prefer Core/GPU Hotspot/Tedge naming)
                    if (sensor.SensorType == SensorType.Temperature)
                    {
                        if (name.Contains("Hot Spot", StringComparison.OrdinalIgnoreCase)
                            || name.Contains("Hotspot", StringComparison.OrdinalIgnoreCase)
                            || name.Contains("Core", StringComparison.OrdinalIgnoreCase)
                            || name.Contains("GPU", StringComparison.OrdinalIgnoreCase)
                            || name.Contains("Edge", StringComparison.OrdinalIgnoreCase))
                        {
                            gpuTemp ??= sensor.Value;
                        }
                    }

                    // VRAM used/total - look for vendor-specific and generic sensors
                    if (sensor.SensorType == SensorType.Data || sensor.SensorType == SensorType.SmallData)
                    {
                        // NVIDIA: generic GPU Memory Used/Free/Total are exposed (SmallData in MB)
                        if (name.Equals("GPU Memory Used", StringComparison.OrdinalIgnoreCase))
                        {
                            var val = sensor.Value; // SmallData is MB
                            if (val.HasValue)
                            {
                                double gb = sensor.SensorType == SensorType.SmallData ? (val.Value / 1024.0) : val.Value;
                                vramUsedGb ??= gb;
                            }
                        }
                        if (name.Equals("GPU Memory Total", StringComparison.OrdinalIgnoreCase))
                        {
                            var val = sensor.Value;
                            if (val.HasValue)
                            {
                                double gb = sensor.SensorType == SensorType.SmallData ? (val.Value / 1024.0) : val.Value;
                                vramTotalGb ??= gb;
                            }
                        }
                        if (name.Equals("GPU Memory Free", StringComparison.OrdinalIgnoreCase))
                        {
                            var val = sensor.Value;
                            if (val.HasValue)
                            {
                                double freeGb = sensor.SensorType == SensorType.SmallData ? (val.Value / 1024.0) : val.Value;
                                if (vramTotalGb.HasValue && !vramUsedGb.HasValue)
                                {
                                    vramUsedGb = Math.Max(0, vramTotalGb.Value - freeGb);
                                }
                            }
                        }

                        // Fallbacks: generic VRAM patterns for other GPU brands
                        if (vramUsedGb == null || vramTotalGb == null)
                        {
                            bool isVramGeneric = name.Contains("VRAM", StringComparison.OrdinalIgnoreCase) ||
                                                 name.Contains("GPU Memory", StringComparison.OrdinalIgnoreCase);

                            if (isVramGeneric && name.Contains("Used", StringComparison.OrdinalIgnoreCase))
                            {
                                var val = sensor.Value;
                                if (val.HasValue)
                                {
                                    double gb = sensor.SensorType == SensorType.SmallData ? (val.Value / 1024.0) : val.Value;
                                    vramUsedGb ??= gb;
                                }
                            }

                            if (isVramGeneric && (name.Contains("Total", StringComparison.OrdinalIgnoreCase) ||
                                                 name.Contains("Dedicated", StringComparison.OrdinalIgnoreCase)))
                            {
                                var val = sensor.Value;
                                if (val.HasValue)
                                {
                                    double gb = sensor.SensorType == SensorType.SmallData ? (val.Value / 1024.0) : val.Value;
                                    vramTotalGb ??= gb;
                                }
                            }
                        }
                    }
                }
            }
        }

        // Derive totals/percentages if needed
        if (ramTotalGb == null && ramUsedGb != null && ramAvailGb != null)
            ramTotalGb = ramUsedGb + ramAvailGb;
        if (ramUsedPct == null && ramUsedGb != null && ramTotalGb != null && ramTotalGb > 0)
            ramUsedPct = (ramUsedGb / ramTotalGb) * 100.0;

        // If we have VRAM used but no total, try to infer per GPU model (fallback mapping)
        if (vramTotalGb == null && vramUsedGb != null && vramUsedGb > 0 && !string.IsNullOrWhiteSpace(gpuModel))
        {
            var model = gpuModel!.ToLowerInvariant();
            // Basic mapping, extend as needed
            var map = new (string pattern, double gb)[]
            {
                ("rtx 4050", 6.0),
                ("rtx 4060", 8.0),
                ("rtx 4070", 12.0),
                ("rtx 4080", 16.0),
                ("rtx 4090", 24.0),
            };
            foreach (var (pattern, gb) in map)
            {
                if (model.Contains(pattern)) { vramTotalGb = gb; break; }
            }
        }

        if (vramUsedPct == null && vramUsedGb != null && vramTotalGb != null && vramTotalGb > 0)
            vramUsedPct = (vramUsedGb / vramTotalGb) * 100.0;

        return new RootMetrics
        {
            cpu = new CpuMetrics { load = cpuLoad, temp_c = cpuTemp },
            ram = new RamMetrics { used_pct = ramUsedPct, used_gb = ramUsedGb, total_gb = ramTotalGb },
            gpu = new GpuMetrics { load = gpuLoad, temp_c = gpuTemp },
            vram = new VramMetrics { used_pct = vramUsedPct, used_gb = vramUsedGb, total_gb = vramTotalGb }
        };
    }

    // Dump all sensors for diagnostics (names, types, values)
    public object SensorsDump()
    {
        _comp.Accept(new UpdateVisitor());

        var list = new List<object>();
        foreach (var hw in _comp.Hardware)
        {
            hw.Update();
            foreach (var sub in hw.SubHardware) sub.Update();

            IEnumerable<IHardware> allHw = new[] { hw }.Concat(hw.SubHardware);
            foreach (var h in allHw)
            {
                foreach (var s in h.Sensors)
                {
                    list.Add(new
                    {
                        hardware = new { name = h.Name, type = h.HardwareType.ToString() },
                        sensor = new
                        {
                            name = s.Name,
                            type = s.SensorType.ToString(),
                            value = s.Value,
                            min = s.Min,
                            max = s.Max
                        }
                    });
                }
            }
        }

        return list;
    }

    public bool IsHealthy()
    {
        // Healthy if we managed to read recently (< 5s) or there is any cached data
        var hasRecent = (DateTime.UtcNow - _lastRead) < TimeSpan.FromSeconds(5);
        return hasRecent || _lastRead != DateTime.MinValue;
    }

    public void Dispose()
    {
        // Computer does not implement IDisposable; Close() is sufficient
        _comp?.Close();
    }

    private sealed class UpdateVisitor : IVisitor
    {
        public void VisitComputer(IComputer computer) => computer.Traverse(this);
        public void VisitHardware(IHardware hardware)
        {
            hardware.Update();
            foreach (var sub in hardware.SubHardware) sub.Accept(this);
        }
        public void VisitSensor(ISensor sensor) { }
        public void VisitParameter(IParameter param) { }
    }
}

// Strongly-typed DTOs with expected JSON names
public sealed class CpuMetrics
{
    public double? load { get; set; }
    [JsonPropertyName("temp_c")] public double? temp_c { get; set; }
}

public sealed class RamMetrics
{
    [JsonPropertyName("used_pct")] public double? used_pct { get; set; }
    [JsonPropertyName("used_gb")] public double? used_gb { get; set; }
    [JsonPropertyName("total_gb")] public double? total_gb { get; set; }
}

public sealed class GpuMetrics
{
    public double? load { get; set; }
    [JsonPropertyName("temp_c")] public double? temp_c { get; set; }
}

public sealed class VramMetrics
{
    [JsonPropertyName("used_pct")] public double? used_pct { get; set; }
    [JsonPropertyName("used_gb")] public double? used_gb { get; set; }
    [JsonPropertyName("total_gb")] public double? total_gb { get; set; }
}

public sealed class RootMetrics
{
    public CpuMetrics cpu { get; set; } = new();
    public RamMetrics ram { get; set; } = new();
    public GpuMetrics gpu { get; set; } = new();
    public VramMetrics vram { get; set; } = new();
}