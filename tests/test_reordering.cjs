// Run with: node --test tests/test_reordering.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const {join} = require('node:path');

// Load the real editor without starting its asynchronous data load. These small
// DOM doubles exercise ordering and input state; browser QA covers real layout.
function editor() {
  function element(top = 0, height = 80) {
    const classes = new Set(), attrs = new Map(), pointers = new Set();
    return {
      children: [], dataset: {}, style: {}, scrollTop: 0, offsetWidth: 120, offsetHeight: 30,
      classList: {add: (...xs) => xs.forEach(x => classes.add(x)), remove: (...xs) => xs.forEach(x => classes.delete(x)), contains: x => classes.has(x)},
      setAttribute: (k, v) => attrs.set(k, v), getAttribute: k => attrs.get(k),
      getBoundingClientRect: () => ({left: 0, right: 500, top, bottom: top + height, height}),
      setPointerCapture: id => pointers.add(id), hasPointerCapture: id => pointers.has(id), releasePointerCapture: id => pointers.delete(id),
      append(...xs) {this.children.push(...xs)}, remove() {}, focus() {}, scrollIntoView() {},
    };
  }
  const elements = new Map([['editPane', element(0, 500)]]), frames = new Map();
  let frame = 0;
  const context = vm.createContext({
    URLSearchParams, structuredClone, location: {search: ''},
    innerWidth: 800, innerHeight: 500,
    document: {
      getElementById(id) {if (!elements.has(id)) elements.set(id, element()); return elements.get(id)},
      createElement: () => element(), querySelectorAll: () => [], body: element(),
    },
    window: {addEventListener() {}}, fetch: () => new Promise(() => {}),
    requestAnimationFrame: fn => {frames.set(++frame, fn); return frame}, cancelAnimationFrame: id => frames.delete(id),
  });
  vm.runInContext(readFileSync(join(__dirname, '../src/app.js'), 'utf8'), context);
  const list = element(0, 300);
  list.children = [element(0), element(100), element(200)];
  const moves = [], handle = context.reorderHandle(list, list.children[0], 'Highlights', 0, false, to => moves.push(to));
  const key = key => handle.onkeydown({key, preventDefault() {}});
  const pointer = (x, y, pointerType = 'mouse') => ({clientX: x, clientY: y, pointerId: 1, pointerType, isPrimary: true, button: 0, preventDefault() {}});
  return {context, list, moves, handle, key, pointer, frames, elements};
}

const plain = value => JSON.parse(JSON.stringify(value));

test('master arbitrary-distance moves keep values and IDs paired, including duplicate text', () => {
  const {context} = editor();
  const arr = ['Same text', 'Second', 'Same text', 'Fourth'];
  const nodes = ['a', 'b', 'c', 'd'].map(id => ({id})), node = {id: 'list', children: nodes.slice()};
  context.reorderItems(arr, node, nodes.map(n => n.id), 0, 3);
  assert.deepEqual(arr, ['Second', 'Same text', 'Fourth', 'Same text']);
  assert.deepEqual(plain(node.children.map(n => n.id)), ['b', 'c', 'd', 'a']);
  assert.equal(node.children[3], nodes[0]);
  context.reorderItems(arr, node, ['b', 'c', 'd', 'a'], 3, 0);
  assert.deepEqual(plain(node.children.map(n => n.id)), ['a', 'b', 'c', 'd']);
});

test('version moves follow displayed IDs and preserve master, exclusions, wording, and indentation', () => {
  const {context} = editor();
  const arr = ['A', 'B', 'C'], node = {id: 'list', children: ['a', 'b', 'c'].map(id => ({id}))};
  const version = {excluded: ['b'], wording: {a: 'alternative'}, indent: {c: 2}, order: {list: ['c', 'a', 'b']}};
  const before = structuredClone({arr, node, version});
  context.reorderItems(arr, node, version.order.list, 2, 0, version);
  assert.deepEqual(plain(version.order.list), ['b', 'c', 'a']);
  assert.deepEqual({arr, node, version: {...version, order: before.version.order}}, before);
});

test('dropping in the same position leaves version order unset', () => {
  const {context} = editor(), version = {};
  assert.equal(context.reorderItems(['A'], {id: 'list', children: [{id: 'a'}]}, ['a'], 0, 0, version), false);
  assert.deepEqual(version, {});
});

test('keyboard pickup chooses a position and commits only on drop', () => {
  const {key, handle, list, moves, elements} = editor();
  key(' '); key('End');
  assert.deepEqual(moves, []);
  assert.ok(list.children[2].classList.contains('drop-after'));
  key('Enter');
  assert.deepEqual(moves, [2]);
  assert.equal(handle.getAttribute('aria-pressed'), 'false');
  assert.equal(elements.get('reorderStatus').textContent, 'Moved highlights item to position 3 of 3.');
});

test('Escape, focus loss, and rerender cancel keyboard moves without committing', () => {
  for (const cancel of ['escape', 'blur', 'render']) {
    const {key, handle, list, moves, context} = editor();
    key('Enter'); key('ArrowDown');
    if (cancel === 'escape') key('Escape');
    if (cancel === 'blur') handle.onblur();
    if (cancel === 'render') vm.runInContext('cancelReorder()', context);
    assert.deepEqual(moves, []);
    assert.equal(handle.getAttribute('aria-pressed'), 'false');
    assert.ok(list.children.every(x => !x.classList.contains('drop-before') && !x.classList.contains('drag-source')));
  }
});

for (const pointerType of ['mouse', 'touch']) test(`${pointerType} dragging commits the destination and releases capture`, () => {
  const {handle, pointer, moves, frames} = editor();
  handle.onpointerdown(pointer(30, 20, pointerType));
  handle.onpointermove(pointer(30, 270, pointerType));
  handle.onpointerup(pointer(30, 270, pointerType));
  assert.deepEqual(moves, [2]);
  assert.equal(handle.hasPointerCapture(1), false);
  assert.equal(frames.size, 0);
});

test('pointer cancellation, outside drops, and accidental taps do not reorder', () => {
  for (const action of ['cancel', 'outside', 'tap']) {
    const {handle, pointer, moves, frames} = editor();
    handle.onpointerdown(pointer(30, 20));
    if (action !== 'tap') handle.onpointermove(pointer(30, 270));
    if (action === 'cancel') handle.onpointercancel();
    else handle.onpointerup(pointer(action === 'outside' ? 600 : 30, action === 'tap' ? 20 : 270));
    assert.deepEqual(moves, []);
    assert.equal(frames.size, 0);
  }
});

test('dragging scrolls near the visible viewport edge on a small screen', () => {
  const {context, handle, pointer, elements} = editor();
  context.innerHeight = 300;
  handle.onpointerdown(pointer(30, 20));
  handle.onpointermove(pointer(30, 290));
  assert.ok(elements.get('editPane').scrollTop > 0);
  handle.onpointercancel();
});
