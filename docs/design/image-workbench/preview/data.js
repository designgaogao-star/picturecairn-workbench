/* Safe, local design fixtures. None of these IDs address a real gallery. */
window.WORKBENCH_DATA = (() => {
  const photos = [
    ['lake', '湖畔清晨', 1600, 1067, 360653],
    ['coast', '海岸来信', 1600, 1067, 204855],
    ['mountain', '山野之间', 1000, 667, 180301],
    ['forest', '林间散步', 1000, 666, 219279],
    ['waves', '潮汐记录', 1000, 667, 65691],
    ['valley', '夏日山谷', 1000, 667, 185192],
    ['trees', '森林深处', 1000, 690, 220443],
    ['snow', '星空与雪山', 1000, 667, 147342],
    ['reflection', '群山倒影', 1000, 667, 120053],
    ['mist', '雨后木桥', 1000, 667, 255268],
    ['desert', '旷野之西', 1000, 662, 133007],
    ['architecture', '建筑的线条', 1000, 1500, 343758],
  ].map(([id, name, width, height, bytes]) => ({ id, name, width, height, bytes, src: `assets/${id}.jpg` }));
  const groups = [
    { id: 'travel', name: '旅行影像', category: '非R18', state: 'none', photoIds: [...photos.filter((p) => p.id !== 'reflection').map((p) => p.id), 'lake-copy'] },
    { id: 'mountains', name: '山川湖泊', category: '非R18', state: 'kept', photoIds: ['lake', 'mountain', 'valley', 'snow', 'reflection'] },
    { id: 'seaside', name: '海岸与远行', category: '非R18', state: 'marked', photoIds: ['coast', 'waves', 'desert'] },
    { id: 'woods', name: '森林手记', category: '非R18', state: 'none', photoIds: ['forest', 'trees', 'mist'] },
    { id: 'buildings', name: '建筑观察', category: '非R18', state: 'none', photoIds: ['architecture'] },
    { id: 'unfiled', name: '未归档', category: '其他', state: 'none', photoIds: [] },
  ];
  const packages = (groupId) => {
    const group = groups.find((g) => g.id === groupId) || groups[0];
    return group.photoIds.map((id, i) => {
      const photo = photos.find((p) => p.id === (id === 'lake-copy' ? 'lake' : id));
      const name = photo.name + (id === 'lake-copy' ? ' · 完整版' : '');
      return { id: `${group.id}-${id}`, groupId: group.id, name, photo, count: 8,
        rel: `${group.name}/${i < 6 ? '精选' : '沿途'}/${name}`, parent: i < 6 ? '精选' : '沿途' };
    });
  };
  const images = (pkg) => {
    const start = photos.indexOf(pkg.photo);
    return Array.from({ length: pkg.count }, (_, i) => {
      const photo = photos[(start + i) % photos.length];
      return { ...photo, id: `${pkg.id}-${i + 1}`, name: `${String(i + 1).padStart(3, '0')}_${photo.name}.jpg`,
        rel: `${pkg.rel}/${String(i + 1).padStart(3, '0')}_${photo.name}.jpg`, index: i, packageId: pkg.id };
    });
  };
  return { photos, groups, packages, images };
})();
