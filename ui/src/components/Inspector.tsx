import { bytes, count, stripCategory } from '../lib/format';
import { Icon } from '../lib/icons';
import { currentGroup, currentPackage } from '../state/app';
import { inspection, inspectionScope, inspectorOpen } from '../state/inspection';
import { markLabel } from './Marks';
import { SidePanel } from './SidePanel';

export function Inspector() {
  const current = inspection.value;
  const items = current?.scope === inspectionScope() ? current.items : [];
  const resource = items.length === 1 ? items[0] : null;
  const group = currentGroup.value;
  const pkg = currentPackage.value;
  const rows: [string, string][] = [];
  let title = '当前文件夹';
  let name = group ? stripCategory(group.name) || '（根目录）' : '…';
  if (items.length > 1) {
    title = '所选项目'; name = `已选 ${count(items.length)} 项`;
    const images = items.filter((item) => item.kind === 'image');
    if (images.length === items.length) rows.push(['总大小', bytes(images.reduce((sum, item) => sum + item.item.size, 0))]);
    rows.push(['范围', group?.rel || '（图库根目录）']);
  } else if (resource?.kind === 'image') {
    const item = resource.item;
    title = '图片信息'; name = item.name;
    rows.push(['尺寸', item.width && item.height ? `${item.width} × ${item.height}` : '待补齐'], ['大小', bytes(item.size)],
      ['动图', item.animated == null ? '待补齐' : item.animated ? '是' : '否'], ['相对位置', item.rel]);
    if (item.error) rows.push(['读取错误', item.error]);
  } else if (resource?.kind === 'package' || pkg) {
    const item = resource?.kind === 'package' ? resource.item : pkg!;
    title = '图包信息'; name = item.loose ? '散图' : item.name;
    rows.push(['图片', `${count(item.image_count)} 张`], ['相对位置', item.rel || '（图库根目录）']);
  } else if (group) {
    rows.push(['图片', `${count(group.image_count)} 张`], ['总大小', bytes(group.bytes)], ['文件夹状态', markLabel(group.state)], ['相对位置', group.rel || '（图库根目录）']);
  }
  return <SidePanel class="inspector" label="信息面板" onClose={() => { inspectorOpen.value = false; }}>
    <header class="inspector-head"><h2>{title}</h2><button class="icon-btn" title="关闭信息" aria-label="关闭信息" onClick={() => { inspectorOpen.value = false; }}><Icon name="X" /></button></header>
    <div class="inspector-body"><h3>{name}</h3><dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd class={label === '读取错误' ? 'bad' : ''}>{value}</dd></div>)}</dl></div>
  </SidePanel>;
}
