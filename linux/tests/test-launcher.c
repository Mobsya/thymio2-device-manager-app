/* Exercise real GTK windows, child processes and AppIndicator registration.
 * Run only from build/launcher-tests, beside a disposable backend fixture. */
#define main launcher_main
#include "../thymio-2-device-manager.c"
#undef main

static void iterate_for(gint milliseconds)
{
    gint64 deadline = g_get_monotonic_time() + milliseconds * 1000;
    do {
        while (g_main_context_iteration(NULL, FALSE)) {}
        g_usleep(1000);
    } while (g_get_monotonic_time() < deadline);
}

static void wait_for_exit(AppState *state)
{
    gint64 deadline = g_get_monotonic_time() + 3 * G_TIME_SPAN_SECOND;
    while (state->process != NULL && g_get_monotonic_time() < deadline) {
        iterate_for(10);
    }
    g_assert_null(state->process);
}

static void write_backend(const gchar *script)
{
    gchar *path = get_tdm_path();
    gchar *directory = g_path_get_dirname(path);
    gchar *basename = g_path_get_basename(directory);
    /* Never replace the supplied backend, even if the test is run incorrectly. */
    g_assert_cmpstr(basename, ==, "launcher-tests");
    if (script == NULL) {
        g_unlink(path);
    } else {
        g_assert_true(g_file_set_contents(path, script, -1, NULL));
        g_assert_cmpint(g_chmod(path, 0700), ==, 0);
    }
    g_free(basename);
    g_free(directory);
    g_free(path);
}

static void start_app(AppState *state)
{
    static guint instance;
    GError *error = NULL;
    gchar *id = g_strdup_printf("org.mobsya.launcher-test.t%u", ++instance);
    state->app = gtk_application_new(id, G_APPLICATION_NON_UNIQUE);
    g_free(id);
    gboolean registered = g_application_register(G_APPLICATION(state->app), NULL, &error);
    g_assert_no_error(error);
    g_assert_true(registered);
    on_activate(G_APPLICATION(state->app), state);
    g_assert_true(gtk_widget_get_visible(state->window));
}

static void stop_app(AppState *state)
{
    gchar *icon_dir = g_strdup(state->icon_dir);
    request_quit(state);
    wait_for_exit(state);
    on_shutdown(G_APPLICATION(state->app), state);
    g_assert_false(g_file_test(icon_dir, G_FILE_TEST_EXISTS));
    g_free(icon_dir);
    g_clear_object(&state->app);
    iterate_for(20);
    write_backend(NULL);
}

static gboolean run_in_subprocess(void)
{
    if (g_test_subprocess()) {
        return TRUE;
    }
    /* GtkApplication owns process-global state. Give each lifecycle a process. */
    g_test_trap_subprocess(NULL, 10 * G_TIME_SPAN_SECOND, G_TEST_SUBPROCESS_DEFAULT);
    g_test_trap_assert_passed();
    return FALSE;
}

static void test_no_tray_and_errors(void)
{
    if (!run_in_subprocess()) return;
    AppState state = {0};
    write_backend(NULL);
    start_app(&state);
    g_assert_null(state.process);
    g_assert_nonnull(strstr(gtk_label_get_text(GTK_LABEL(state.status_label)), "Could not start"));
    g_assert_false(state.tray_connected);

    write_backend("#!/bin/sh\nexit 23\n");
    launch_tdm(&state);
    gtk_widget_hide(state.window);
    wait_for_exit(&state);
    g_assert_true(gtk_widget_get_visible(state.window));
    g_assert_nonnull(strstr(gtk_label_get_text(GTK_LABEL(state.status_label)), "exit status 23"));

    write_backend("#!/bin/sh\nexec sleep 60\n");
    launch_tdm(&state);
    GSubprocess *original = state.process;
    gtk_widget_hide(state.window);
    on_activate(G_APPLICATION(state.app), &state);
    g_assert_true(gtk_widget_get_visible(state.window));
    g_assert_true(original == state.process);
    on_menu_about(NULL, &state);
    GtkWidget *about = state.about_dialog;
    on_menu_about(NULL, &state);
    g_assert_true(about == state.about_dialog);
    g_assert_cmpstr(gtk_about_dialog_get_version(GTK_ABOUT_DIALOG(about)), ==, APP_VERSION " (" APP_BUILD ")");
    gtk_dialog_response(GTK_DIALOG(about), GTK_RESPONSE_CLOSE);
    g_assert_null(state.about_dialog);
    g_assert_true(on_window_delete(state.window, NULL, &state));
    g_assert_true(state.quitting);
    wait_for_exit(&state);
    g_assert_cmpuint(state.quit_timeout, ==, 0);
    stop_app(&state);
}

static void test_forced_quit(void)
{
    if (!run_in_subprocess()) return;
    AppState state = {0};
    write_backend("#!/bin/sh\ntrap '' TERM\nexec sleep 60\n");
    start_app(&state);
    iterate_for(100);
    GSubprocess *process = g_object_ref(state.process);
    request_quit(&state);
    guint timeout = state.quit_timeout;
    request_quit(&state);
    g_assert_cmpuint(state.quit_timeout, ==, timeout);
    wait_for_exit(&state);
    g_assert_true(g_subprocess_get_if_signaled(process));
    g_assert_cmpint(g_subprocess_get_term_sig(process), ==, SIGKILL);
    g_object_unref(process);
    stop_app(&state);
}

static gboolean registered_indicator;

static void register_indicator(GDBusConnection *connection, const gchar *sender,
    const gchar *path, const gchar *interface, const gchar *method,
    GVariant *parameters, GDBusMethodInvocation *invocation, gpointer data)
{
    (void) connection; (void) sender; (void) path; (void) interface; (void) data;
    const gchar *item_path;
    g_assert_cmpstr(method, ==, "RegisterStatusNotifierItem");
    g_variant_get(parameters, "(&s)", &item_path);
    g_assert_true(g_variant_is_object_path(item_path));
    registered_indicator = TRUE;
    g_dbus_method_invocation_return_value(invocation, NULL);
}

static void test_indicator_and_tray_loss(void)
{
    if (!run_in_subprocess()) return;
    const gchar *xml = "<node><interface name='org.kde.StatusNotifierWatcher'>"
        "<method name='RegisterStatusNotifierItem'><arg type='s' direction='in'/></method>"
        "</interface></node>";
    const GDBusInterfaceVTable vtable = { .method_call = register_indicator };
    GDBusNodeInfo *info = g_dbus_node_info_new_for_xml(xml, NULL);
    GDBusConnection *bus = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, NULL);
    guint object = g_dbus_connection_register_object(bus, "/StatusNotifierWatcher",
        info->interfaces[0], &vtable, NULL, NULL, NULL);
    guint owner = g_bus_own_name_on_connection(bus, "org.kde.StatusNotifierWatcher",
        G_BUS_NAME_OWNER_FLAGS_NONE, NULL, NULL, NULL, NULL);
    g_assert_cmpuint(object, !=, 0);
    AppState state = {0};
    write_backend("#!/bin/sh\nexec sleep 60\n");
    start_app(&state);
    gint64 deadline = g_get_monotonic_time() + 3 * G_TIME_SPAN_SECOND;
    while ((!registered_indicator || !state.tray_connected) && g_get_monotonic_time() < deadline) {
        iterate_for(10);
    }
    g_assert_true(registered_indicator);
    g_assert_true(state.tray_connected);
    g_assert_true(g_file_test(app_indicator_get_icon(state.indicator), G_FILE_TEST_IS_REGULAR));
    g_assert_cmpint(app_indicator_get_status(state.indicator), ==, APP_INDICATOR_STATUS_ACTIVE);

    on_window_delete(state.window, NULL, &state);
    g_assert_false(gtk_widget_get_visible(state.window));
    g_assert_false(state.quitting);
    g_assert_nonnull(state.process);
    /* Exercise the actual tray menu signal. */
    GList *items = gtk_container_get_children(GTK_CONTAINER(state.menu));
    gtk_menu_item_activate(GTK_MENU_ITEM(items->data));
    g_assert_true(gtk_widget_get_visible(state.window));
    gtk_widget_hide(state.window);

    g_bus_unown_name(owner);
    deadline = g_get_monotonic_time() + 3 * G_TIME_SPAN_SECOND;
    while (state.tray_connected && g_get_monotonic_time() < deadline) {
        iterate_for(10);
    }
    g_assert_false(state.tray_connected);
    g_assert_true(gtk_widget_get_visible(state.window));
    gtk_menu_item_activate(GTK_MENU_ITEM(g_list_last(items)->data));
    g_list_free(items);
    wait_for_exit(&state);
    stop_app(&state);
    g_dbus_connection_unregister_object(bus, object);
    g_dbus_node_info_unref(info);
    g_object_unref(bus);
}

int main(int argc, char **argv)
{
    gtk_init(&argc, &argv);
    g_test_init(&argc, &argv, NULL);
    /* Ayatana's GTK3 implementation emits its own deprecation warnings. */
    g_log_set_always_fatal(G_LOG_LEVEL_ERROR | G_LOG_LEVEL_CRITICAL);
    g_test_add_func("/launcher/no-tray-and-errors", test_no_tray_and_errors);
    g_test_add_func("/launcher/forced-quit", test_forced_quit);
    g_test_add_func("/launcher/indicator-and-tray-loss", test_indicator_and_tray_loss);
    return g_test_run();
}
