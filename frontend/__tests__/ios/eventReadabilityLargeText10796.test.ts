import { readFileSync } from 'fs';
import { join } from 'path';

const root = join(__dirname, '../../../ios/Bain Luck/Bain Luck');
const read = (path: string) => readFileSync(join(root, path), 'utf8')
  .replace(/\/\/[^\n]*/g, '');

describe('#10796 larger text keeps the numbers and the plot readable', () => {
  it('all four verdict slots use the width policy of the restacked hero', () => {
    const page = read('Views/EventDetailView.swift');
    expect(page).toMatch(/let stacked = dynamicTypeSize >= \.xxLarge/);
    expect(page).toMatch(/size >= \.xxLarge \? nil : verdictSlotWidth/);
    expect(page.match(/\.frame\(maxWidth: Self\.heroVerdictWidth\(at: dynamicTypeSize\)/g)).toHaveLength(4);
    expect(page).not.toMatch(/\.frame\(maxWidth: (?:Self|EventDetailView)\.verdictSlotWidth/);
  });

  it.each(['OddsChartView', 'ScoreDifferentialChartView'])('%s budgets the axes and team labels together', name => {
    const chart = read(`Components/${name}.swift`);
    expect(chart).toContain('EventChartTypography.labelSize(scaled: scaledAxisFontSize)');
    expect(chart).toContain('let gutterFont = axisFontSize');
    expect(chart).not.toMatch(/let gutterFont: CGFloat = \d+/);
    expect(chart).toContain('xAxisContextTicks(');
    expect(chart).toContain('labelScale: axisFontSize / 9');
    expect(chart).toContain('reservedRow(format: plan.format, fontSize: axisFontSize)');
    expect(chart).toContain('.padding(.top, axisFontSize / 2)');
    expect(chart).not.toContain('.dynamicTypeSize(');
  });

  it('drawn dates share the bounded axis font instead of scaling independently', () => {
    const labels = read('Components/ChartTimeAxisLabels.swift');
    expect(labels).toContain('min(max(scaled, 12), 16)');
    expect(labels).toContain('EventChartTypography.labelSize(scaled: scaledFontSize)');
  });

  it('a scoring threshold grows its column and stays an indivisible number', () => {
    const spectrum = read('Components/TotalPointsSpectrumView.swift');
    expect(spectrum).toContain('@ScaledMetric(relativeTo: .caption) private var thresholdColumnWidth');
    const label = spectrum.slice(spectrum.indexOf('Text("\\(formatThreshold(threshold))+"'));
    expect(label).toMatch(/^Text\([^\n]+\)\s*\.font\([^\n]+\)\s*\.lineLimit\(1\)\s*\.fixedSize\(horizontal: true, vertical: false\)\s*\.frame\(minWidth: thresholdColumnWidth, alignment: \.leading\)/);
  });
});
