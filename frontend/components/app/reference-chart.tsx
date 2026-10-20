import Image from "next/image";

const BARS = [{"color":"#9161f5","height":36,"left":304,"top":83},{"color":"#50adff","height":49,"left":291,"top":70},{"color":"#50adff","height":61,"left":278,"top":58},{"color":"#9161f5","height":43,"left":265,"top":76},{"color":"#50adff","height":28,"left":252,"top":91},{"color":"#50adff","height":31,"left":239,"top":88},{"color":"#9161f5","height":57,"left":226,"top":62},{"color":"#50adff","height":48,"left":213,"top":71},{"color":"#50adff","height":62,"left":200,"top":57},{"color":"#9161f5","height":42,"left":187,"top":77},{"color":"#50adff","height":55,"left":174,"top":64},{"color":"#50adff","height":47,"left":161,"top":72},{"color":"#9161f5","height":36,"left":148,"top":83},{"color":"#50adff","height":41,"left":135,"top":78},{"color":"#50adff","height":52,"left":122,"top":67},{"color":"#9161f5","height":33,"left":109,"top":86},{"color":"#50adff","height":47,"left":96,"top":72},{"color":"#50adff","height":30,"left":83,"top":89},{"color":"#9161f5","height":43,"left":70,"top":76},{"color":"#50adff","height":36,"left":57,"top":83},{"color":"#50adff","height":25,"left":44,"top":94}];
const LAYERS = [
  { metric: "spend", name: "img4", width: 297.265, height: 89.6136, left: 30.4376, top: 15.1024 },
  { metric: "conversions", name: "img3", width: 296.535, height: 89.5, left: 31, top: 15.252 },
  { metric: "cpa", name: "imgCpa", width: 296.96, height: 89.3817, left: 30.5856, top: 15.252 },
];

// The initial demo view uses the original Figma vectors; period comparison uses the data chart.
export function ReferenceChart({ metric, labels }: { metric: "all" | "spend" | "conversions" | "cpa"; labels: string[] }) {
  return <div className="reference-chart-wrap"><div className="reference-chart" role="img" aria-label="Демонстрационная динамика расходов, конверсий и CPA">
    {[800,600,400,200,0].map((value,i)=><div className="reference-chart-grid" key={value} style={{top:9+i*29.5}}><span>{value ? value+"K" : "0"}</span></div>)}
    {BARS.map((bar,i)=><span key={i} className="reference-chart-bar" style={{left:bar.left,top:bar.top,height:bar.height,background:`linear-gradient(180deg,${bar.color},#1a477a)`}}/>)}
    {LAYERS.filter(layer=>metric==="all"||metric===layer.metric).map(layer=><Image key={layer.metric} src={`/figma/liquid/6-40708-${layer.name}.svg`} alt="" unoptimized width={layer.width} height={layer.height} style={{left:layer.left,top:layer.top}} className="reference-chart-line"/>)}
    {labels.map((label,i)=><span key={label+i} className="reference-chart-label" style={{left:32+i*45}}>{label}</span>)}
  </div></div>;
}

