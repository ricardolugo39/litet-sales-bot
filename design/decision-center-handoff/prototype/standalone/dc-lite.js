/*
 * dc-lite.js: a minimal offline runner for the Decision Center prototype.
 *
 * It renders the subset of the Design-canvas ".dc.html" format that the
 * prototype uses: {{path}} holes in text and attributes, <sc-if>, <sc-for>,
 * onClick / onChange handlers, and a DCLogic class with state/setState.
 * It exists only so the prototype can be opened without the canvas.
 * It is NOT part of the Flask app and must not be shipped with it.
 *
 * build.py rewrites <sc-if>/<sc-for> to <template data-if>/<template data-for>
 * so the HTML parser keeps them inside tables.
 */
(function () {
  'use strict';

  function lookup(scope, path) {
    path = path.trim();
    if (path === 'true') return true;
    if (path === 'false') return false;
    if (path !== '' && !isNaN(Number(path))) return Number(path);
    var parts = path.split('.');
    var v = scope;
    for (var i = 0; i < parts.length; i++) {
      if (v == null) return undefined;
      v = v[parts[i]];
    }
    return v;
  }

  var WHOLE = /^\s*\{\{([^}]+)\}\}\s*$/;
  var HOLE = /\{\{([^}]+)\}\}/g;

  function interp(str, scope) {
    return str.replace(HOLE, function (_, p) {
      var v = lookup(scope, p);
      return v == null ? '' : String(v);
    });
  }

  function isTpl(node, kind) {
    return node.nodeType === 1 && node.localName === 'template' && node.hasAttribute('data-' + kind);
  }

  function kids(node) {
    return node.content ? node.content.childNodes : node.childNodes;
  }

  function renderNodes(nodes, scope, parent) {
    for (var i = 0; i < nodes.length; i++) renderNode(nodes[i], scope, parent);
  }

  function renderNode(node, scope, parent) {
    if (node.nodeType === 3) {
      parent.appendChild(document.createTextNode(interp(node.nodeValue, scope)));
      return;
    }
    if (node.nodeType !== 1) return;

    if (isTpl(node, 'if')) {
      var cond = lookup(scope, (node.getAttribute('value') || '').replace(/[{}]/g, ''));
      if (cond) renderNodes(kids(node), scope, parent);
      return;
    }
    if (isTpl(node, 'for')) {
      var list = lookup(scope, (node.getAttribute('list') || '').replace(/[{}]/g, '')) || [];
      var as = node.getAttribute('as') || 'item';
      for (var j = 0; j < list.length; j++) {
        var child = Object.create(scope);
        child[as] = list[j];
        child.$index = j;
        renderNodes(kids(node), child, parent);
      }
      return;
    }

    var el = node.namespaceURI && node.namespaceURI !== 'http://www.w3.org/1999/xhtml'
      ? document.createElementNS(node.namespaceURI, node.localName)
      : document.createElement(node.localName);

    for (var a = 0; a < node.attributes.length; a++) {
      var attr = node.attributes[a];
      var name = attr.name, raw = attr.value;
      if (name.indexOf('hint-') === 0) continue;
      var m = raw.match(WHOLE);
      if (/^on[A-Z]/.test(name) || /^on[a-z]+$/.test(name) && m) {
        var fn = m ? lookup(scope, m[1]) : null;
        if (typeof fn === 'function') {
          var evt = name.slice(2).toLowerCase();
          if (evt === 'change' && (node.localName === 'input' || node.localName === 'textarea')) evt = 'input';
          el.addEventListener(evt, fn);
        }
        continue;
      }
      var val = m ? lookup(scope, m[1]) : interp(raw, scope);
      if (val == null || val === false) continue;
      if (name === 'value' && node.localName === 'input') { el.value = String(val); continue; }
      el.setAttribute(name, val === true ? '' : String(val));
    }

    if (node.localName === 'template') {
      renderNodes(node.content.childNodes, scope, el.content || el);
    } else {
      renderNodes(node.childNodes, scope, el);
    }
    parent.appendChild(el);
  }

  var current = null;

  function DCLogic(props) {
    this.props = props || {};
    this.state = {};
  }
  DCLogic.prototype.setState = function (patch) {
    var next = typeof patch === 'function' ? patch(this.state, this.props) : patch;
    this.state = Object.assign({}, this.state, next);
    if (current && current.instance === this) current.schedule();
  };
  DCLogic.prototype.forceUpdate = function () {
    if (current && current.instance === this) current.schedule();
  };

  function mount(opts) {
    var tpl = document.getElementById(opts.templateId);
    var root = document.getElementById(opts.rootId);
    var Comp = opts.Component;
    var instance = new Comp(opts.props || {});
    if (!instance.state) instance.state = {};
    var pending = false;

    function render() {
      pending = false;
      var active = document.activeElement;
      var focusKey = active && active.getAttribute && active.getAttribute('aria-label');
      var selStart = active && 'selectionStart' in active ? active.selectionStart : null;
      var scope = instance.renderVals ? instance.renderVals() : {};
      var frag = document.createDocumentFragment();
      renderNodes(tpl.content.childNodes, scope, frag);
      root.replaceChildren(frag);
      if (focusKey) {
        var again = root.querySelector('[aria-label="' + focusKey.replace(/"/g, '\\"') + '"]');
        if (again && again.tagName === 'INPUT') {
          again.focus();
          if (selStart != null) { try { again.setSelectionRange(selStart, selStart); } catch (e) {} }
        }
      }
    }

    current = {
      instance: instance,
      schedule: function () {
        if (pending) return;
        pending = true;
        (window.requestAnimationFrame || setTimeout)(render);
      }
    };
    render();
    if (instance.componentDidMount) instance.componentDidMount();
    return instance;
  }

  window.DCLogic = DCLogic;
  window.dcLite = { mount: mount };
})();
