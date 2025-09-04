using LibreHardwareMonitor.Hardware;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using System.Text.Json;
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

builder.Services.AddSingleton<SensorReader>();

var app = builder.Build();

app.MapGet("/metrics", (SensorReader reader) =>
{
    var data = reader.Read();
    return Results.Text(JsonSerializer.Serialize(data), "application/json");
});

// Diagnostic endpoint: list all hardware and sensors with current values
app.MapGet("/sensors", (SensorReader reader) =>
{
    var data = reader.SensorsDump();
    return Results.Text(JsonSerializer.Serialize(data, new JsonSerializerOptions { WriteIndented = true }), "application/json");
});

app.Run();

public sealed class SensorReader : IDisposable
{
    private readonly Computer _comp;

    public SensorReader()
    {
        _comp = new Computer
        {
            IsCpuEnabled = true,
            IsGpuEnabled = true, // optional GPU from LHM
            IsMemoryEnabled = true,
            IsStorageEnabled = false,
            IsMotherboardEnabled = false,
            IsNetworkEnabled = false
        };
        _comp.Open();
    }

    public object Read()
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
                        var name = sensor.Name;
                        if (name.Contains("Used", StringComparison.OrdinalIgnoreCase) && name.Contains("Memory", StringComparison.OrdinalIgnoreCase))
                            ramUsedGb ??= sensor.Value;
                        if (name.Contains("Available", StringComparison.OrdinalIgnoreCase) && name.Contains("Memory", StringComparison.OrdinalIgnoreCase))
                            ramAvailGb ??= sensor.Value;
                        if (name.Contains("Total", StringComparison.OrdinalIgnoreCase) && name.Contains("Memory", StringComparison.OrdinalIgnoreCase))
                            ramTotalGb ??= sensor.Value;
                    }
                }
            }
            else if (hw.HardwareType == HardwareType.GpuNvidia || hw.HardwareType == HardwareType.GpuAmd || hw.HardwareType == HardwareType.GpuIntel)
            {
                // Update sensors for this hardware and its sub-hardware to ensure latest readings
                hw.Update();
                foreach (var sub in hw.SubHardware) sub.Update();

                // Collect sensors including sub-hardware
                IEnumerable<ISensor> allSensors = hw.Sensors
                    .Concat(hw.SubHardware.SelectMany(sh => sh.Sensors));

                foreach (var sensor in allSensors)
                {
                    var name = sensor.Name ?? string.Empty;
                    
                    // Debug: log all GPU sensors to console
                    Console.WriteLine($"[DEBUG] GPU Sensor: {name} ({sensor.SensorType}) = {sensor.Value}");

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

                    // VRAM usage percent - look for D3D load sensors
                    if (sensor.SensorType == SensorType.Load &&
                        (name.Contains("D3D", StringComparison.OrdinalIgnoreCase) ||
                         name.Contains("VRAM", StringComparison.OrdinalIgnoreCase)))
                    {
                        // Prefer D3D 3D if available, else keep previous generic picks
                        if (name.Equals("D3D 3D", StringComparison.OrdinalIgnoreCase) || name.Equals("GPU Core", StringComparison.OrdinalIgnoreCase) || name.Equals("GPU", StringComparison.OrdinalIgnoreCase))
                        {
                            gpuLoad ??= sensor.Value;
                        }
                    }

                    // VRAM used/total - look for D3D Shared Memory sensors
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

                        // For total VRAM, we'll need to use a fallback approach since it's not directly exposed
                        // RTX 4050 has 6GB VRAM - we can hardcode this or try to detect it
                        if (name.Contains("Shared Memory", StringComparison.OrdinalIgnoreCase) && 
                            name.Contains("Total", StringComparison.OrdinalIgnoreCase))
                        {
                            var val = sensor.Value;
                            if (val.HasValue)
                            {
                                double gb = sensor.SensorType == SensorType.SmallData ? (val.Value / 1024.0) : val.Value;
                                vramTotalGb ??= gb;
                            }
                        }

                        // Fallback: generic VRAM patterns for other GPU brands
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
        
        // For NVIDIA RTX 4050, if we have VRAM used but no total, assume 6GB total
        if (vramTotalGb == null && vramUsedGb != null && vramUsedGb > 0)
        {
            vramTotalGb = 6.0; // RTX 4050 has 6GB VRAM
        }
        
        if (vramUsedPct == null && vramUsedGb != null && vramTotalGb != null && vramTotalGb > 0)
            vramUsedPct = (vramUsedGb / vramTotalGb) * 100.0;

        return new
        {
            cpu = new { load = cpuLoad, temp_c = cpuTemp },
            ram = new { used_pct = ramUsedPct, used_gb = ramUsedGb, total_gb = ramTotalGb },
            gpu = new { load = gpuLoad, temp_c = gpuTemp },
            vram = new { used_pct = vramUsedPct, used_gb = vramUsedGb, total_gb = vramTotalGb }
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