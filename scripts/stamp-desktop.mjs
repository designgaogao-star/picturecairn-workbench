import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NtExecutable, NtExecutableResource } from 'pe-library';
import { Data, Resource } from 'resedit';

const project = fileURLToPath(new URL('../', import.meta.url));
const [source, target] = process.argv.slice(2);
assert.ok(source && target && path.isAbsolute(source) && path.isAbsolute(target), 'Provide absolute source and staged output executable paths');
assert.notEqual(path.resolve(source).toLowerCase(), path.resolve(target).toLowerCase(), 'Write a new staged executable');
const packageInfo = JSON.parse(await readFile(path.join(project, 'package.json'), 'utf8'));
const executable = NtExecutable.from(await readFile(source), { ignoreCert: true });
const resources = NtExecutableResource.from(executable);
const icon = Data.IconFile.from(await readFile(path.join(project, 'output/brand/runtime/app.ico')));
const groups = Resource.IconGroupEntry.fromEntries(resources.entries);
assert.ok(groups.length, 'The staged Electron executable has no icon group');
for (const group of groups) {
  Resource.IconGroupEntry.replaceIconsForResource(resources.entries, group.id, group.lang, icon.icons.map((item) => item.data));
}
const versions = Resource.VersionInfo.fromEntries(resources.entries);
assert.ok(versions.length, 'The staged Electron executable has no version resource');
for (const info of versions) {
  for (const language of info.getAvailableLanguages()) {
    info.setStringValues(language, { ProductName: packageInfo.productName, FileDescription: packageInfo.productName,
      CompanyName: 'Stillmark contributors',
      InternalName: 'StillmarkWorkbench', OriginalFilename: 'GalleryTool.exe',
      LegalCopyright: 'Copyright Stillmark contributors. MIT License.' });
    info.setFileVersion('0.0.0.0', language.lang);
    info.setProductVersion('0.0.0.0', language.lang);
    info.setStringValues(language, { FileVersion: packageInfo.releaseLabel, ProductVersion: packageInfo.releaseLabel });
  }
  info.outputToResourceEntries(resources.entries);
}
resources.outputResource(executable);
await writeFile(target, Buffer.from(executable.generate()), { flag: 'wx' });
const checked = NtExecutableResource.from(NtExecutable.from(await readFile(target)));
assert.ok(Resource.IconGroupEntry.fromEntries(checked.entries).every((group) => group.icons.length === 7));
for (const version of Resource.VersionInfo.fromEntries(checked.entries)) {
  assert.ok(version.getAvailableLanguages().every((language) => {
    const strings = version.getStringValues(language);
    return strings.ProductName === packageInfo.productName && strings.ProductVersion === packageInfo.releaseLabel
      && strings.FileVersion === packageInfo.releaseLabel;
  }));
  assert.equal(version.fixedInfo.fileVersionMS | version.fixedInfo.fileVersionLS
    | version.fixedInfo.productVersionMS | version.fixedInfo.productVersionLS, 0);
}
console.log('Stamped unsigned development preview: seven icon sizes and unpublished build metadata verified');
