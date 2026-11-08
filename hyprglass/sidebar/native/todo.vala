namespace SwayNotificationCenter.Widgets {
    public class Todo : BaseWidget {
        public override string widget_name { get { return "todo"; } }

        Gtk.Box tasks;
        Gtk.Entry entry;
        Gtk.Label status;
        bool busy = false;
        uint refresh_timer = 0;
        string last_snapshot = "";

        public Todo (string suffix) {
            base (suffix);
            orientation = Gtk.Orientation.VERTICAL;
            spacing = 8;
            vexpand = true;

            var header = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var add = new Gtk.Button.with_label ("+");
            add.set_tooltip_text ("Add a task to today's note");
            add.add_css_class ("todo-add");
            add.clicked.connect (() => command.begin ({ "ensure" }));
            var title = new Gtk.Label ("Todo");
            title.add_css_class ("todo-title");
            title.xalign = 0;
            title.hexpand = true;
            header.append (title);
            header.append (add);
            append (header);

            tasks = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            var scroller = new Gtk.ScrolledWindow ();
            scroller.set_policy (Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC);
            scroller.add_css_class ("todo-scroll");
            scroller.set_min_content_height (120);
            scroller.vexpand = true;
            scroller.set_child (tasks);
            append (scroller);

            entry = new Gtk.Entry ();
            entry.placeholder_text = "Add a task…";
            entry.visible = false;
            entry.activate.connect (() => {
                string text = entry.text.strip ();
                if (text.length > 0) command.begin ({ "add", text });
            });
            append (entry);

            status = new Gtk.Label ("");
            status.wrap = true;
            status.xalign = 0;
            status.visible = false;
            status.add_css_class ("todo-error");
            append (status);

            map.connect (() => {
                command.begin ({ "list" });
                if (refresh_timer == 0) {
                    refresh_timer = Timeout.add_seconds (30, () => {
                        command.begin ({ "list" });
                        return Source.CONTINUE;
                    });
                }
            });
            unmap.connect (() => {
                if (refresh_timer != 0) {
                    Source.remove (refresh_timer);
                    refresh_timer = 0;
                }
            });
        }

        async void command (owned string[] arguments) {
            if (busy) return;
            busy = true;
            sensitive = false;
            status.visible = false;
            try {
                string helper = Environment.get_variable ("HYPR_GLASS_COMMAND")
                    ?? Path.build_filename (Environment.get_home_dir (), ".config", "hypr", "bin", "hypr-glass");
                string[] argv = { helper, "notes" };
                foreach (string argument in arguments) argv += argument;
                var process = new Subprocess.newv (argv,
                    SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                string output;
                string errors;
                yield process.communicate_utf8_async (null, null, out output, out errors);
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                var snapshot = parser.get_root ().get_object ();
                if (!process.get_successful ()) {
                    throw new IOError.FAILED (snapshot.get_string_member_with_default ("error", "Could not update today's note."));
                }
                if (last_snapshot != output) {
                    render (snapshot.get_array_member ("tasks"));
                    last_snapshot = output;
                }
                if (arguments[0] == "ensure") entry.visible = true;
                if (arguments[0] == "add") entry.text = "";
            } catch (Error error) {
                if (last_snapshot.length > 0 && arguments[0] == "toggle") {
                    try {
                        var previous = new Json.Parser ();
                        previous.load_from_data (last_snapshot);
                        render (previous.get_root ().get_object ().get_array_member ("tasks"));
                    } catch (Error ignored) { }
                }
                status.label = error.message;
                status.visible = true;
            }
            sensitive = true;
            busy = false;
            if (entry.visible && arguments[0] != "list") entry.grab_focus ();
        }

        void render (Json.Array snapshot) {
            while (tasks.get_first_child () != null) tasks.remove (tasks.get_first_child ());
            if (snapshot.get_length () == 0) {
                var empty = new Gtk.Label ("No tasks today");
                empty.xalign = 0;
                empty.add_css_class ("todo-empty");
                tasks.append (empty);
            }
            foreach (unowned Json.Node node in snapshot.get_elements ()) {
                var task = node.get_object ();
                string line = task.get_int_member ("line").to_string ();
                string fingerprint = task.get_string_member ("fingerprint");
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
                var check = new Gtk.CheckButton ();
                check.hexpand = true;
                var text = new Gtk.Label (task.get_string_member ("text"));
                text.wrap = true;
                text.wrap_mode = Pango.WrapMode.WORD_CHAR;
                text.xalign = 0;
                text.hexpand = true;
                check.set_child (text);
                check.active = task.get_boolean_member ("done");
                check.toggled.connect (() => command.begin ({ "toggle", line, fingerprint, check.active.to_string () }));
                var remove = new Gtk.Button.from_icon_name ("edit-delete-symbolic");
                string delete_label = "Delete task: " + task.get_string_member ("text");
                remove.set_tooltip_text (delete_label);
                remove.update_property (Gtk.AccessibleProperty.LABEL, delete_label, -1);
                remove.add_css_class ("todo-delete");
                remove.valign = Gtk.Align.CENTER;
                remove.clicked.connect (() => command.begin ({ "delete", line, fingerprint }));
                row.append (check);
                row.append (remove);
                tasks.append (row);
            }
        }
    }
}
