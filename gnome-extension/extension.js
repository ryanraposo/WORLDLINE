/* Read-only window frame API. This extension never activates windows or sends input. */
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS = 'org.worldline.WindowFrames';
const PATH = '/org/worldline/WindowFrames';
const XML = `<node>
  <interface name="org.worldline.WindowFrames">
    <method name="GetVersion"><arg type="u" direction="out"/></method>
    <method name="GetRects"><arg type="s" direction="out"/></method>
  </interface>
</node>`;

export default class WorldlineWindowFrames extends Extension {
    enable() {
        this._connection = Gio.DBus.session;
        this._object = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._object.export(this._connection, PATH);
        this._owner = Gio.bus_own_name_on_connection(
            this._connection, BUS, Gio.BusNameOwnerFlags.NONE, null, null);
    }

    disable() {
        if (this._owner) {
            Gio.bus_unown_name(this._owner);
            this._owner = 0;
        }
        if (this._object) {
            this._object.unexport();
            this._object = null;
        }
        this._connection = null;
    }

    GetVersion() {
        return 1;
    }

    GetRects() {
        const actors = global.get_window_actors();
        const frames = [];
        for (let stacking = 0; stacking < actors.length; stacking++) {
            const actor = actors[stacking];
            const window = actor.meta_window;
            if (!window || window.get_window_type() === Meta.WindowType.DESKTOP ||
                window.get_window_type() === Meta.WindowType.DOCK)
                continue;
            const rect = window.get_frame_rect();
            const pid = window.get_pid();
            // Match CUA's native window_id using Mutter's session-scoped stable sequence.
            const id = window.get_stable_sequence();
            if (!Number.isInteger(pid) || pid <= 0 || !Number.isInteger(id) ||
                rect.width <= 0 || rect.height <= 0)
                continue;
            frames.push({
                pid, id, x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                title: window.get_title() || '',
                focused: window.has_focus(),
                visible: !window.is_hidden(),
                minimized: window.minimized,
                stacking,
            });
        }
        return JSON.stringify(frames);
    }
}
