/* Interactive D3 views for the clickstream network and Redfin housing panel. */
const DATA_DIR = "data/processed/";
const fmt = d3.format(",d");
const compact = d3.format("~s");
const tooltip = d3.select("#tooltip");
const housingMonthCache = new Map();

function loadHousingMonth(month) {
  if (!housingMonthCache.has(month)) {
    housingMonthCache.set(month, d3.json(`${DATA_DIR}redfin/months/${month}.json`));
  }
  return housingMonthCache.get(month);
}

function monthLabel(value) {
  return d3.timeFormat("%b %Y")(new Date(`${value}-01T00:00:00`));
}

function formatHousing(metric, value) {
  if (value == null || !Number.isFinite(+value)) return "Not reported";
  const n = +value;
  if (["sale_price", "new_listing_price"].includes(metric)) return `$${d3.format(",.0f")(n)}`;
  if (["sale_price_yoy", "sale_to_list_ratio", "above_list_share"].includes(metric)) return `${d3.format("+.1f")(n)}%`;
  if (metric === "days_on_market_yoy") return `${d3.format("+.1f")(n)} days`;
  if (metric === "days_on_market") return `${d3.format(".1f")(n)} days`;
  if (metric === "months_supply") return `${d3.format(".1f")(n)} months`;
  return fmt(Math.round(n));
}

function showTooltip(html, event) {
  tooltip.html(html).style("display", "block")
    .style("left", `${Math.min(event.clientX + 14, window.innerWidth - 380)}px`)
    .style("top", `${Math.min(event.clientY + 14, window.innerHeight - 110)}px`);
}
function hideTooltip() { tooltip.style("display", "none"); }
function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;"}[c]));
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
    document.querySelectorAll(".panel").forEach((panel) => panel.classList.toggle("active-panel", panel.id === button.dataset.target));
  });
});

Promise.all([
  d3.json(`${DATA_DIR}summary.json`),
  d3.json(`${DATA_DIR}network.json`),
  d3.json(`${DATA_DIR}redfin/summary.json`),
]).then(([summary, network, housing]) => {
  document.querySelector("#network-coverage").textContent =
    `Core graph: ${fmt(network.summary.nodes_available)} high-activity pages and ${fmt(network.summary.displayed_edges)} directed page-to-page edges. ` +
    `The displayed core retains ${(network.summary.displayed_share_of_all_link_clicks * 100).toFixed(2)}% of all internal-link click weight. ` +
    "Redfin housing views use a separate monthly metro panel.";
  const latest = housing.latest;
  document.querySelector("#distribution-insights").innerHTML =
    `<b>Housing panel:</b> ${fmt(housing.source_rows)} metro-month records across ${fmt(housing.region_count)} metros and ${fmt(housing.state_count)} state/DC groups, ${esc(housing.date_start)}–${esc(housing.date_end)}. ` +
    `<b>Latest month (${esc(latest.month)}):</b> cross-metro median sale price ${formatHousing("sale_price", latest.median_sale_price)}, ` +
    `${formatHousing("sale_price_yoy", latest.median_sale_price_yoy)} year-over-year; median days on market ${formatHousing("days_on_market", latest.median_days_on_market)}; ` +
    `median inventory ${fmt(latest.median_inventory)}. Market-size tiers are fixed from each metro’s 2024–2025 median homes sold.`;
  initNetwork(network);
  initRedfinParallel(housing);
  initRedfinTreemap(housing);
}).catch((error) => {
  console.error(error);
  document.querySelector("#network-coverage").textContent = "Dashboard data missing. Run prepare_infovis.py and prepare_redfin.py first.";
});

function initNetwork(data) {
  const svg = d3.select("#network-chart");
  const width = 1440, height = 820;
  const margin = {top: 50, right: 55, bottom: 46, left: 55};
  svg.attr("viewBox", `0 0 ${width} ${height}`);
  svg.append("defs").append("marker").attr("id", "edge-arrow").attr("viewBox", "0 -5 10 10")
    .attr("refX", 17).attr("refY", 0).attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto")
    .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#718095");
  const edgeLayer = svg.append("g"), nodeLayer = svg.append("g"), labelLayer = svg.append("g");
  const nodeSlider = document.querySelector("#node-count");
  nodeSlider.max = data.nodes.length;
  const edgeSlider = document.querySelector("#edge-threshold");
  const communityColor = (id) => d3.schemeTableau10[Number(id) % d3.schemeTableau10.length];
  let selectedPage = null;
  let visibleNodes = [];

  for (const layout of ["spring", "kamada_kawai", "forceatlas2"]) {
    const preview = d3.select(`#preview-${layout}`).attr("viewBox", "0 0 420 230");
    const positions = new Map(data.nodes.map((d) => [d.page, [210 + d.layouts[layout][0] * 190, 112 - d.layouts[layout][1] * 96]]));
    preview.append("g").selectAll("line").data(data.edges).join("line")
      .attr("x1", (d) => positions.get(d.source)[0]).attr("y1", (d) => positions.get(d.source)[1])
      .attr("x2", (d) => positions.get(d.target)[0]).attr("y2", (d) => positions.get(d.target)[1]);
    preview.append("g").selectAll("circle").data(data.nodes).join("circle")
      .attr("cx", (d) => positions.get(d.page)[0]).attr("cy", (d) => positions.get(d.page)[1])
      .attr("r", 2.5).attr("fill", (d) => communityColor(d.community));
  }

  function render() {
    const n = +nodeSlider.value;
    const layout = document.querySelector("#layout-select").value;
    const threshold = 10 ** (+edgeSlider.value);
    visibleNodes = data.nodes.slice(0, n);
    const nodeSet = new Set(visibleNodes.map((d) => d.page));
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;
    const points = new Map(visibleNodes.map((d) => [d.page, [margin.left + (d.layouts[layout][0] + 1) * innerW / 2,
      margin.top + (1 - (d.layouts[layout][1] + 1) / 2) * innerH]]));
    const edges = data.edges.filter((e) => nodeSet.has(e.source) && nodeSet.has(e.target) && e.clicks >= threshold);
    const widthScale = d3.scaleSqrt().domain(d3.extent(data.edges, (d) => d.clicks)).range([0.5, 4.8]);
    const edgeSelection = edgeLayer.selectAll("path.network-edge").data(edges, (d) => `${d.source}\t${d.target}`);
    edgeSelection.exit().remove();
    edgeSelection.enter().append("path").attr("class", "network-edge").attr("marker-end", "url(#edge-arrow)")
      .merge(edgeSelection)
      .attr("d", (d) => {
        const [x1, y1] = points.get(d.source), [x2, y2] = points.get(d.target);
        if (d.source === d.target) return `M${x1},${y1} C${x1 + 35},${y1 - 42} ${x1 - 35},${y1 - 42} ${x1},${y1}`;
        const dx = x2 - x1, dy = y2 - y1, curve = Math.min(50, Math.hypot(dx, dy) * 0.08);
        return `M${x1},${y1} Q${(x1 + x2) / 2 - dy / (Math.hypot(dx,dy)||1) * curve},${(y1 + y2) / 2 + dx / (Math.hypot(dx,dy)||1) * curve} ${x2},${y2}`;
      })
      .attr("stroke-width", (d) => widthScale(d.clicks))
      .on("mousemove", (event, d) => showTooltip(`<b>${esc(d.source)}</b> → <b>${esc(d.target)}</b><br>${fmt(d.clicks)} clicks`, event))
      .on("mouseleave", hideTooltip);

    const radius = d3.scaleSqrt().domain(d3.extent(data.nodes, (d) => d.activity)).range([5, 22]);
    const nodes = nodeLayer.selectAll("circle.network-node").data(visibleNodes, (d) => d.page);
    nodes.exit().remove();
    nodes.enter().append("circle").attr("class", "network-node")
      .merge(nodes)
      .attr("cx", (d) => points.get(d.page)[0]).attr("cy", (d) => points.get(d.page)[1])
      .attr("r", (d) => radius(d.activity)).attr("fill", (d) => communityColor(d.community))
      .on("click", (event, d) => { event.stopPropagation(); selectedPage = selectedPage === d.page ? null : d.page; applySelection(); })
      .on("mousemove", (event, d) => showTooltip(
        `<b>${esc(d.page)}</b><br>Community ${Number(d.community) + 1}<br>In: ${fmt(d.in_clicks)} clicks · ${fmt(d.in_degree)} source pages<br>Out: ${fmt(d.out_clicks)} clicks · ${fmt(d.out_degree)} destinations`, event))
      .on("mouseleave", hideTooltip);

    const labelLimit = document.querySelector("#show-labels").checked ? 24 : 0;
    const labelNodes = visibleNodes.slice().sort((a, b) => b.activity - a.activity).slice(0, labelLimit);
    labelLayer.selectAll("text").data(labelNodes, (d) => d.page).join("text").attr("class", "network-label")
      .attr("x", (d) => points.get(d.page)[0] + radius(d.activity) + 3)
      .attr("y", (d) => points.get(d.page)[1] + 3).text((d) => d.page.replaceAll("_", " ").slice(0, 28));
    document.querySelector("#node-count-value").textContent = fmt(n);
    document.querySelector("#edge-threshold-value").textContent = fmt(Math.round(threshold));
    const search = document.querySelector("#node-search").value.trim().toLowerCase();
    if (search) selectedPage = visibleNodes.find((d) => d.page.toLowerCase().includes(search))?.page || null;
    applySelection();
  }

  function applySelection() {
    const connected = new Set();
    if (selectedPage) {
      connected.add(selectedPage);
      for (const e of data.edges) if (e.source === selectedPage || e.target === selectedPage) { connected.add(e.source); connected.add(e.target); }
    }
    nodeLayer.selectAll("circle.network-node")
      .attr("opacity", (d) => !selectedPage || connected.has(d.page) ? 0.94 : 0.14)
      .attr("stroke", (d) => d.page === selectedPage ? "#152334" : "white")
      .attr("stroke-width", (d) => d.page === selectedPage ? 3.2 : 1.6);
    edgeLayer.selectAll("path.network-edge")
      .classed("is-highlight", (d) => selectedPage && (d.source === selectedPage || d.target === selectedPage))
      .attr("opacity", (d) => !selectedPage || d.source === selectedPage || d.target === selectedPage ? 1 : 0.12);
    document.querySelector("#network-detail").textContent = selectedPage
      ? `Selected ${selectedPage}. Highlighted nodes are direct incoming or outgoing neighbors. Click the node again or Clear selection to reset.`
      : `Hover over a page or edge for details. Click a page to highlight its immediate neighbors. Current layout: ${document.querySelector("#layout-select").selectedOptions[0].text}.`;
  }

  svg.on("click", () => { selectedPage = null; applySelection(); });
  ["#layout-select", "#node-count", "#edge-threshold", "#show-labels"].forEach((selector) => document.querySelector(selector).addEventListener("input", render));
  document.querySelector("#node-search").addEventListener("input", render);
  document.querySelector("#clear-node").addEventListener("click", () => { selectedPage = null; document.querySelector("#node-search").value = ""; applySelection(); });
  document.querySelectorAll(".layout-preview").forEach((button) => button.addEventListener("click", () => {
    document.querySelector("#layout-select").value = button.dataset.layout;
    render();
    document.querySelector("#network-panel").scrollIntoView({behavior:"smooth", block:"start"});
  }));
  render();
}

const TIER_NAMES = ["Small-volume", "Medium-low", "Medium-high", "High-volume"];
const TIER_COLORS = ["#4774a8", "#43a18b", "#e6a344", "#cb5b50"];

function initRedfinParallel(summary) {
  const svg=d3.select("#parallel-chart"), width=1500, height=850;
  const margin={top:135,right:65,bottom:70,left:65}, top=margin.top, bottom=height-margin.bottom;
  svg.attr("viewBox",`0 0 ${width} ${height}`);
  const monthSelect=document.querySelector("#parallel-month");
  summary.months.forEach((month)=>monthSelect.add(new Option(monthLabel(month),month)));
  monthSelect.value=summary.date_end;
  const tierColor=d3.scaleOrdinal(TIER_NAMES,TIER_COLORS), toggleBox=document.querySelector("#tier-toggles");
  toggleBox.innerHTML=TIER_NAMES.map((tier)=>`<label><input type="checkbox" checked value="${esc(tier)}"> ${esc(tier)}</label>`).join("");
  document.querySelector("#bundle-legend").innerHTML=TIER_NAMES.map((tier)=>
    `<span class="legend-item"><i class="legend-swatch" style="background:${tierColor(tier)}"></i>${esc(tier)}</span>`).join("");
  const axisDefs=[
    {key:"sale_price",label:"Median sale price ($)",transform:(v)=>Math.log10(Math.max(v,1)),tick:(v)=>`$${compact(10**v)}`},
    {key:"sale_price_yoy",label:"Sale-price change YoY (%)",transform:(v)=>v,tick:(v)=>`${v.toFixed(0)}%`},
    {key:"homes_sold",label:"Homes sold (log)",transform:(v)=>Math.log10(Math.max(v,0)+1),tick:(v)=>compact(Math.max(0,Math.round(10**v-1)))},
    {key:"active_listings",label:"Active listings (log)",transform:(v)=>Math.log10(Math.max(v,0)+1),tick:(v)=>compact(Math.max(0,Math.round(10**v-1)))},
    {key:"days_on_market",label:"Days on market (log)",transform:(v)=>Math.log10(Math.max(v,0)+1),tick:(v)=>`${Math.max(0,Math.round(10**v-1))}d`},
    {key:"months_supply",label:"Months of supply (log)",transform:(v)=>Math.log10(Math.max(v,0)+1),tick:(v)=>`${Math.max(0,Math.round(10**v-1))}m`},
    {key:"tier",label:"Fixed metro-size tier",categorical:true},
  ];
  const axisByKey=new Map(axisDefs.map((axis)=>[axis.key,axis]));
  let dimensions=axisDefs.map((axis)=>axis.key), currentMonth=summary.date_end, requestId=0, visible=[], selectedCount=0, scales={};
  const brushes=new Map(), xPositions=new Map(), line=d3.line().curve(d3.curveCatmullRom.alpha(.5));

  function transformed(row,key) {
    if(key==="tier") return TIER_NAMES.indexOf(row.tier);
    const raw=row[key];
    return raw==null||!Number.isFinite(+raw)?null:axisByKey.get(key).transform(+raw);
  }
  function draw(rows) {
    svg.selectAll("*").remove();
    const chosen=rows.filter((row)=>toggleBox.querySelector(`input[value="${CSS.escape(row.tier)}"]`)?.checked);
    visible=chosen.filter((row)=>dimensions.every((key)=>Number.isFinite(transformed(row,key))));
    selectedCount=chosen.length;
    const x=d3.scalePoint(dimensions,[margin.left,width-margin.right]).padding(.035);
    dimensions.forEach((key)=>xPositions.set(key,x(key)));
    scales={};
    for(const key of dimensions) {
      const def=axisByKey.get(key);
      if(def.categorical) scales[key]=d3.scalePoint(TIER_NAMES,[bottom,top]).padding(.3);
      else {
        const vals=visible.map((row)=>transformed(row,key)).filter(Number.isFinite).sort(d3.ascending);
        let lo=d3.quantileSorted(vals,.02), hi=d3.quantileSorted(vals,.98);
        if(!Number.isFinite(lo)||!Number.isFinite(hi)||lo===hi){lo=Number.isFinite(lo)?lo:0;hi=Number.isFinite(hi)&&hi!==lo?hi:lo+1;}
        scales[key]=d3.scaleLinear().domain([lo,hi]).nice(5).range([bottom,top]).clamp(true);
      }
    }
    const centers=new Map();
    for(const [tier,group] of d3.group(visible,(row)=>row.tier))
      centers.set(tier,Object.fromEntries(dimensions.map((key)=>[key,d3.median(group,(row)=>transformed(row,key))])));
    const strength=+document.querySelector("#bundle-strength").value;
    function yFor(row,key) {
      if(key==="tier") return scales[key](row.tier);
      const value=transformed(row,key); return value==null?null:scales[key](value);
    }
    function pathFor(row) {
      const points=[];
      for(let i=0;i<dimensions.length;i++) {
        const key=dimensions[i],actual=yFor(row,key),median=centers.get(row.tier)?.[key];
        if(!Number.isFinite(actual)) return null;
        const center=key==="tier"?scales[key](row.tier):scales[key](median??transformed(row,key));
        points.push([xPositions.get(key),(i===0||i===dimensions.length-1)?actual:actual*(1-strength)+center*strength]);
      }
      return line(points);
    }
    const paths=svg.append("g").attr("class","housing-lines").selectAll("path").data(visible,(row)=>row.region_id).join("path")
      .attr("class","parallel-line").attr("d",pathFor).attr("stroke",(row)=>tierColor(row.tier)).attr("stroke-width",1.05)
      .on("mousemove",(event,row)=>showTooltip(
        `<b>${esc(row.region)}</b> · ${esc(row.state)}<br>${esc(row.tier)} metro · ${monthLabel(currentMonth)}<br>`+
        `Median sale price: ${formatHousing("sale_price",row.sale_price)}<br>Price change YoY: ${formatHousing("sale_price_yoy",row.sale_price_yoy)}<br>`+
        `Homes sold: ${formatHousing("homes_sold",row.homes_sold)} · Active listings: ${formatHousing("active_listings",row.active_listings)}<br>`+
        `Days on market: ${formatHousing("days_on_market",row.days_on_market)} · Months of supply: ${formatHousing("months_supply",row.months_supply)}`,event))
      .on("mouseleave",hideTooltip);
    const axes=svg.append("g").attr("class","axes").selectAll("g.dimension").data(dimensions,(key)=>key).join("g")
      .attr("class","dimension").attr("transform",(key)=>`translate(${xPositions.get(key)},0)`);
    axes.each(function(key) {
      const group=d3.select(this),def=axisByKey.get(key);
      const axis=def.categorical?d3.axisLeft(scales[key]).tickSize(5):d3.axisLeft(scales[key]).ticks(6).tickFormat(def.tick);
      group.append("g").attr("class","axis").call(axis);
      group.append("text").attr("class","axis-title").attr("text-anchor","middle").attr("y",margin.top-28)
        .text(def.label).call(wrapAxisTitle,155);
      const brush=d3.brushY().extent([[-13,top],[13,bottom]]).on("end",(event)=>{
        if(!event.sourceEvent)return;
        if(event.selection)brushes.set(key,event.selection);else brushes.delete(key);
        applyBrushes();
      });
      group.append("g").attr("class","brush").call(brush);
      if(brushes.has(key))group.select(".brush").call(brush.move,brushes.get(key));
      group.call(d3.drag().filter((event)=>!event.target.closest?.(".brush"))
        .on("drag",(event,dimension)=>{
          const px=Math.max(margin.left,Math.min(width-margin.right,event.x));
          xPositions.set(dimension,px);
          d3.select(event.sourceEvent.target.closest("g.dimension")).attr("transform",`translate(${px},0)`);
          paths.attr("d",pathFor);
        }).on("end",()=>{dimensions.sort((a,b)=>xPositions.get(a)-xPositions.get(b));draw(rows);}));
    });
    document.querySelector("#bundle-value").textContent=strength.toFixed(2);
    applyBrushes();
  }
  function applyBrushes() {
    const paths=svg.selectAll("path.parallel-line");
    paths.classed("is-muted",(row)=>{
      for(const [key,selection] of brushes) {
        const raw=key==="tier"?scales[key](row.tier):(transformed(row,key)==null?null:scales[key](transformed(row,key)));
        if(!Number.isFinite(raw)||raw<Math.min(selection[0][1],selection[1][1])||raw>Math.max(selection[0][1],selection[1][1]))return true;
      }
      return false;
    });
    const passing=paths.filter(function(){return !d3.select(this).classed("is-muted");}).size();
    document.querySelector("#parallel-detail").textContent=
      `${passing.toLocaleString()} of ${visible.length.toLocaleString()} plotted metros pass ${brushes.size} active brush${brushes.size===1?"":"es"} for ${monthLabel(currentMonth)}; ${selectedCount-visible.length} rows with missing axis values are omitted. Lines bend toward their tier median between axes.`;
  }
  function wrapAxisTitle(selection,maxWidth) {
    selection.each(function(){
      const text=d3.select(this),words=text.text().split(/\s+/).reverse(),x=text.attr("x"),y=text.attr("y");
      let word,lineWords=[],lineNo=0; text.text(null);
      let span=text.append("tspan").attr("x",x).attr("y",y);
      while((word=words.pop())) {
        lineWords.push(word);span.text(lineWords.join(" "));
        if(span.node().getComputedTextLength()>maxWidth&&lineWords.length>1){
          lineWords.pop();span.text(lineWords.join(" "));lineWords=[word];
          span=text.append("tspan").attr("x",x).attr("y",y).attr("dy",`${++lineNo*1.05}em`).text(word);
        }
      }
    });
  }
  async function loadMonth(month) {
    const id=++requestId;
    try { const data=await loadHousingMonth(month);if(id!==requestId)return;currentMonth=month;brushes.clear();draw(data.metros); }
    catch(error){console.error(error);document.querySelector("#parallel-detail").textContent=`Could not load ${month}; rerun prepare_redfin.py.`;}
  }
  monthSelect.addEventListener("change",()=>loadMonth(monthSelect.value));
  document.querySelector("#bundle-strength").addEventListener("input",async()=>{const data=await loadHousingMonth(currentMonth);draw(data.metros);});
  toggleBox.addEventListener("change",async()=>{const data=await loadHousingMonth(currentMonth);draw(data.metros);});
  loadMonth(currentMonth);
}

function initRedfinTreemap(summary) {
  const monthSelect=document.querySelector("#treemap-month");
  summary.months.forEach((month)=>monthSelect.add(new Option(monthLabel(month),month)));
  monthSelect.value=summary.date_end;
  const sizeSelect=document.querySelector("#treemap-size"),colorSelect=document.querySelector("#treemap-color"),modelSelect=document.querySelector("#treemap-model");
  const svg=d3.select("#treemap-chart"),width=1400,height=760;
  svg.attr("viewBox",`0 0 ${width} ${height}`);
  const breadcrumbs=d3.select("#treemap-breadcrumbs");
  let rows=[],root=null,focus=null,currentMonth=summary.date_end,monthRequest=0;
  const areaLabels={homes_sold:"Homes sold",active_listings:"Active listings",inventory:"Inventory",pending_sales:"Pending sales"};
  const colorLabels={sale_price:"Median sale price",sale_price_yoy:"Sale-price change YoY",days_on_market:"Days on market"};

  function hierarchyData() {
    const leaves=rows.map((row)=>({name:row.region,area:+row[sizeSelect.value]||0,row}));
    const byState=d3.group(leaves,(leaf)=>leaf.row.state);
    let children;
    if(modelSelect.value==="state") {
      children=Array.from(byState,([state,metros])=>({name:state,children:metros}));
      document.querySelector("#treemap-method").textContent="Geographic remodeling: state → metro. Select a month and additive area measure; color maps the chosen market indicator.";
    } else {
      const byTier=d3.group(leaves,(leaf)=>leaf.row.tier);
      children=Array.from(byTier,([tier,metros])=>({name:tier,children:Array.from(d3.group(metros,(leaf)=>leaf.row.state),([state,stateMetros])=>({name:state,children:stateMetros}))}));
      document.querySelector("#treemap-method").textContent="Market remodeling: fixed homes-sold tier → state → metro. Tiers use each metro’s 2024–2025 median monthly sales.";
    }
    return {name:"All metro areas",children};
  }
  function colorScale() {
    const key=colorSelect.value,values=rows.map((row)=>row[key]).filter(Number.isFinite);
    if(key==="sale_price_yoy") {
      const sorted=values.slice().sort(d3.ascending),lo=d3.quantile(sorted,.05),hi=d3.quantile(sorted,.95);
      const domain=lo===hi?[lo-1,hi+1]:[lo,hi];
      return {scale:d3.scaleSequential(d3.interpolateReds).domain(domain).clamp(true),min:lo,max:hi};
    }
    if(key==="sale_price") {
      const ext=d3.extent(values),domain=ext[0]===ext[1]?[ext[0]-1,ext[1]+1]:ext;
      return {scale:d3.scaleSequential(d3.interpolateViridis).domain(domain).clamp(true),min:ext[0],max:ext[1]};
    }
    const sorted=values.slice().sort(d3.ascending),lo=d3.quantile(sorted,.05),hi=d3.quantile(sorted,.95);
    const domain=lo===hi?[lo-1,hi+1]:[lo,hi];
    return {scale:d3.scaleSequential(d3.interpolateYlOrBr).domain(domain).clamp(true),min:lo,max:hi};
  }
  function build() {
    const data=hierarchyData(),areaKey=sizeSelect.value,colorKey=colorSelect.value,colorInfo=colorScale();
    root=d3.hierarchy(data).sum((node)=>node.children?0:(+node.area||0)).sort((a,b)=>b.value-a.value);
    root.eachAfter((node)=>{
      if(!node.children) {
        node.colorValue=node.data.row[colorKey];
        node.metroCount=1;
        for(const key of ["sale_price","sale_price_yoy","days_on_market"])node.measures={...(node.measures||{}),[key]:node.data.row[key]};
      }
      else {
        const children=node.children.filter((child)=>Number.isFinite(child.colorValue)&&child.value>0),weight=d3.sum(children,(child)=>child.value);
        node.colorValue=weight?d3.sum(children,(child)=>child.colorValue*child.value)/weight:null;
        node.metroCount=d3.sum(node.children,(child)=>child.metroCount||0);
        node.measures={};
        for(const key of ["sale_price","sale_price_yoy","days_on_market"]) {
          const valid=node.children.filter((child)=>Number.isFinite(child.measures?.[key])&&child.value>0),total=d3.sum(valid,(child)=>child.value);
          node.measures[key]=total?d3.sum(valid,(child)=>child.measures[key]*child.value)/total:null;
        }
      }
    });
    d3.treemap().size([width,height]).paddingInner(2).paddingOuter(2).paddingTop((node)=>node.depth===0?2:22).round(true)(root);
    focus=root;draw(colorInfo,areaKey,colorKey);
    document.querySelector("#treemap-legend").innerHTML=
      `<span>${esc(colorLabels[colorKey])}</span><i class="treemap-gradient ${colorKey==="sale_price_yoy"?"red-sequential":colorKey==="days_on_market"?"amber-sequential":""}"></i><span>${esc(formatHousing(colorKey,colorInfo.min))}</span><span class="legend-spacer"></span><span>${esc(formatHousing(colorKey,colorInfo.max))}</span>${colorKey!=="sale_price"?'<small>Central 90% scale; hover for exact values</small>':""}`;
  }
  function draw(colorInfo,areaKey,colorKey) {
    const sx=d3.scaleLinear().domain([focus.x0,focus.x1]).range([0,width]),sy=d3.scaleLinear().domain([focus.y0,focus.y1]).range([0,height]);
    const children=focus.children||[],cells=svg.selectAll("g.treemap-cell").data(children,(node)=>`${node.data.name}-${node.depth}`);
    cells.exit().transition().duration(160).style("opacity",0).remove();
    const enter=cells.enter().append("g").attr("class","treemap-cell").style("opacity",0);
    enter.append("rect");enter.append("text").attr("class","name-label");enter.append("text").attr("class","value-label");
    const merged=enter.merge(cells).on("click",(event,node)=>{if(node.children){focus=node;draw(colorInfo,areaKey,colorKey);}});
    merged.transition().duration(200).style("opacity",1);
    merged.select("rect").transition().duration(200).attr("x",(node)=>sx(node.x0)).attr("y",(node)=>sy(node.y0))
      .attr("width",(node)=>Math.max(0,sx(node.x1)-sx(node.x0))).attr("height",(node)=>Math.max(0,sy(node.y1)-sy(node.y0)))
      .attr("fill",(node)=>Number.isFinite(node.colorValue)?colorInfo.scale(node.colorValue):"#b9c0c8");
    merged.select(".name-label").attr("x",(node)=>sx(node.x0)+7).attr("y",(node)=>sy(node.y0)+18)
      .style("display",(node)=>sx(node.x1)-sx(node.x0)>76&&sy(node.y1)-sy(node.y0)>26?null:"none")
      .text((node)=>node.data.name.length>(sx(node.x1)-sx(node.x0))/7?`${node.data.name.slice(0,Math.max(5,Math.floor((sx(node.x1)-sx(node.x0))/7)-1))}…`:node.data.name);
    merged.select(".value-label").attr("x",(node)=>sx(node.x0)+7).attr("y",(node)=>sy(node.y0)+35)
      .style("display",(node)=>sx(node.x1)-sx(node.x0)>105&&sy(node.y1)-sy(node.y0)>48?null:"none")
      .text((node)=>formatHousing(areaKey,node.value));
    merged.on("mousemove",(event,node)=>{
      const share=root.value?100*node.value/root.value:0,colorLine=Number.isFinite(node.colorValue)?`${esc(colorLabels[colorKey])}: ${formatHousing(colorKey,node.colorValue)}`:"Color measure not reported";
      const row=node.data.row,detail=row?`<br>${esc(row.state)} · ${esc(row.tier)} · ${esc(row.region)}<br>Homes sold: ${formatHousing("homes_sold",row.homes_sold)} · Active listings: ${formatHousing("active_listings",row.active_listings)}<br>Inventory: ${formatHousing("inventory",row.inventory)} · Pending sales: ${formatHousing("pending_sales",row.pending_sales)}<br>Median price: ${formatHousing("sale_price",row.sale_price)} · Price change YoY: ${formatHousing("sale_price_yoy",row.sale_price_yoy)}<br>Days on market: ${formatHousing("days_on_market",row.days_on_market)}`:`<br>${fmt(node.metroCount||0)} metros · color averages are weighted by ${areaLabels[areaKey].toLowerCase()}<br>Median price: ${formatHousing("sale_price",node.measures?.sale_price)} · Price change YoY: ${formatHousing("sale_price_yoy",node.measures?.sale_price_yoy)}<br>Days on market: ${formatHousing("days_on_market",node.measures?.days_on_market)}`;
      showTooltip(`<b>${esc(node.data.name)}</b> · ${monthLabel(currentMonth)}<br>${formatHousing(areaKey,node.value)} ${esc(areaLabels[areaKey].toLowerCase())} (${share.toFixed(2)}% of displayed total)<br>${colorLine}${detail}${node.children?"<br>Click to zoom":""}`,event);
    }).on("mouseleave",hideTooltip);
    breadcrumbs.selectAll("button").data(focus.ancestors().reverse()).join("button").text((node)=>node.data.name).on("click",(event,node)=>{focus=node;draw(colorInfo,areaKey,colorKey);});
    document.querySelector("#treemap-detail").textContent=
      `Showing ${focus.data.name}: ${formatHousing(areaKey,focus.value)} ${areaLabels[areaKey].toLowerCase()} across ${children.length} categories for ${monthLabel(currentMonth)}. Click a state or tier to zoom in.`;
  }
  async function loadMonth(month) {
    currentMonth=month;const request=++monthRequest;
    try{const data=await loadHousingMonth(month);if(request!==monthRequest)return;rows=data.metros;build();}
    catch(error){console.error(error);document.querySelector("#treemap-detail").textContent=`Could not load ${month}; rerun prepare_redfin.py.`;}
  }
  monthSelect.addEventListener("change",()=>loadMonth(monthSelect.value));
  [sizeSelect,colorSelect,modelSelect].forEach((control)=>control.addEventListener("change",build));
  loadMonth(currentMonth);
}

