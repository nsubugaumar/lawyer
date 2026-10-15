package com.lexdesk.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.io.ByteArrayInputStream;
import android.util.Base64;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * LexDesk for Android.
 *
 * The app shows the firm's LexDesk web app full screen, so every screen and
 * every change the manager makes appears here at once, with no app update.
 * The native side adds what a phone app needs: links to WhatsApp, the dialler,
 * email and social media open in their own apps; documents are downloaded with
 * the user's session and opened in the phone's viewer; files can be uploaded
 * from the phone; and a friendly screen appears when the office server cannot
 * be reached.
 */
public class MainActivity extends Activity {

    private static final int FILE_CHOOSER = 41;
    private static final String PREFS = "lexdesk";
    private static final String KEY_SERVER = "server_url";

    private WebView web;
    private LinearLayout offline;
    private ProgressBar progress;
    private ValueCallback<Uri[]> pendingUpload;
    private String server;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        server = prefs().getString(KEY_SERVER, BuildConfig.SERVER_URL);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#F7F4EE"));

        web = new WebView(this);
        configureWebView();
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(false);
        progress.setMax(100);
        progress.setProgressTintList(android.content.res.ColorStateList.valueOf(Color.parseColor("#C9A463")));
        root.addView(progress, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(3), Gravity.TOP));

        offline = buildOfflineScreen();
        offline.setVisibility(View.GONE);
        root.addView(offline, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        setContentView(root);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(0, insets.getSystemWindowInsetTop(), 0, insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });

        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else if (!isOnline()) openSavedBriefs();
        else web.loadUrl(server + "/login");
    }

    private void configureWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setSupportMultipleWindows(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setUserAgentString(s.getUserAgentString() + " LexDeskApp/" + BuildConfig.VERSION_NAME);

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);

        web.addJavascriptInterface(new Bridge(), "LexDeskApp");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return openOutside(request.getUrl());
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showOffline(true);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                CookieManager.getInstance().flush();
                warmOfflinePage();
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setProgress(newProgress);
                progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (pendingUpload != null) pendingUpload.onReceiveValue(null);
                pendingUpload = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                try {
                    startActivityForResult(Intent.createChooser(pick, "Choose a file"), FILE_CHOOSER);
                } catch (ActivityNotFoundException e) {
                    pendingUpload = null;
                    return false;
                }
                return true;
            }
        });
    }

    /** Anything that is not LexDesk itself opens in the right app. */
    private boolean openOutside(Uri uri) {
        Uri home = Uri.parse(server);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme();
        boolean ours = (scheme.equals("http") || scheme.equals("https"))
                && home.getHost() != null && home.getHost().equalsIgnoreCase(uri.getHost())
                && home.getPort() == uri.getPort();
        if (ours) return false;
        try {
            Intent intent = scheme.equals("tel") ? new Intent(Intent.ACTION_DIAL, uri) : new Intent(Intent.ACTION_VIEW, uri);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "No app on this phone can open that link.", Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    // ------------------------------------------------------------------ files

    /** Called from the web app (lib/api.ts) to fetch a protected document. */
    private class Bridge {
        @JavascriptInterface
        public void download(String path, String token, String filename, boolean open) {
            if (path == null || !path.startsWith("/api/")) return; // only our own API
            new Thread(() -> saveAndOpen(server + path, token, filename, open)).start();
        }

        /** A document saved for court, opened from the phone with no signal. */
        @JavascriptInterface
        public void openBase64(String filename, String mime, String base64) {
            new Thread(() -> {
                try {
                    byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
                    saveStreamAndOpen(new ByteArrayInputStream(bytes), filename, mime == null || mime.isEmpty() ? "application/octet-stream" : mime, true);
                } catch (Exception e) {
                    new Handler(Looper.getMainLooper()).post(() -> Toast.makeText(MainActivity.this, "That document could not be opened.", Toast.LENGTH_LONG).show());
                }
            }).start();
        }

        @JavascriptInterface
        public String version() {
            return BuildConfig.VERSION_NAME;
        }
    }

    private void saveAndOpen(String url, String token, String filename, boolean open) {
        Handler ui = new Handler(Looper.getMainLooper());
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url).openConnection();
            if (token != null && !token.isEmpty()) conn.setRequestProperty("Authorization", "Bearer " + token);
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(60000);
            if (conn.getResponseCode() != 200) throw new IllegalStateException("HTTP " + conn.getResponseCode());

            String mime = conn.getContentType() == null ? "application/octet-stream" : conn.getContentType().split(";")[0];
            try (InputStream in = conn.getInputStream()) {
                saveStreamAndOpen(in, filename, mime, open);
            }
        } catch (Exception e) {
            ui.post(() -> Toast.makeText(this, "That document could not be opened. Please try again.", Toast.LENGTH_LONG).show());
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private void saveStreamAndOpen(InputStream in, String filename, String mime, boolean open) throws Exception {
        Handler ui = new Handler(Looper.getMainLooper());
        {
            ContentValues values = new ContentValues();
            values.put(MediaStore.Downloads.DISPLAY_NAME, safeName(filename));
            values.put(MediaStore.Downloads.MIME_TYPE, mime);
            values.put(MediaStore.Downloads.RELATIVE_PATH, "Download/LexDesk");
            ContentResolver resolver = getContentResolver();
            Uri item = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (item == null) throw new IllegalStateException("Could not create file");
            try (OutputStream out = resolver.openOutputStream(item)) {
                byte[] buffer = new byte[64 * 1024];
                int n;
                while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
            }
            ui.post(() -> {
                if (open) {
                    Intent view = new Intent(Intent.ACTION_VIEW);
                    view.setDataAndType(item, mime);
                    view.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                    try {
                        startActivity(view);
                    } catch (ActivityNotFoundException e) {
                        Toast.makeText(this, "Saved to Downloads/LexDesk. Install a viewer to open it.", Toast.LENGTH_LONG).show();
                    }
                } else {
                    Toast.makeText(this, "Saved to Downloads/LexDesk", Toast.LENGTH_SHORT).show();
                }
            });
        }
    }

    private static String safeName(String name) {
        String cleaned = name == null ? "document" : name.replaceAll("[\\\\/:*?\"<>|]", "_");
        return cleaned.isEmpty() ? "document" : cleaned;
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER || pendingUpload == null) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK && data != null && data.getData() != null) result = new Uri[]{data.getData()};
        pendingUpload.onReceiveValue(result);
        pendingUpload = null;
    }

    // --------------------------------------------------------- offline screen

    private LinearLayout buildOfflineScreen() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(28), dp(28), dp(28), dp(28));
        box.setBackgroundColor(Color.parseColor("#F7F4EE"));

        TextView title = new TextView(this);
        title.setText("We can't reach the office");
        title.setTextSize(22);
        title.setTypeface(Typeface.SERIF, Typeface.BOLD);
        title.setTextColor(Color.parseColor("#1A2230"));
        title.setGravity(Gravity.CENTER);
        box.addView(title);

        TextView body = new TextView(this);
        body.setText("Check that your phone is online. If you are testing on the office Wi-Fi, make sure the LexDesk computer is switched on.");
        body.setTextSize(15);
        body.setTextColor(Color.parseColor("#4A5568"));
        body.setGravity(Gravity.CENTER);
        body.setPadding(0, dp(10), 0, dp(22));
        box.addView(body);

        Button saved = primaryButton("Open saved court briefs");
        saved.setOnClickListener(v -> openSavedBriefs());
        LinearLayout.LayoutParams savedParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50));
        savedParams.bottomMargin = dp(10);
        box.addView(saved, savedParams);

        Button retry = new Button(this);
        retry.setText("Try again");
        retry.setAllCaps(false);
        retry.setOnClickListener(v -> {
            web.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
            showOffline(false);
            web.loadUrl(server + "/login");
        });
        box.addView(retry, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50)));

        TextView label = new TextView(this);
        label.setText("Server address");
        label.setTextSize(13);
        label.setTextColor(Color.parseColor("#6B7280"));
        label.setPadding(0, dp(28), 0, dp(6));
        box.addView(label);

        EditText address = new EditText(this);
        address.setText(server);
        address.setSingleLine(true);
        address.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        box.addView(address, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        Button save = new Button(this);
        save.setText("Use this address");
        save.setAllCaps(false);
        save.setOnClickListener(v -> {
            String value = address.getText().toString().trim().replaceAll("/+$", "");
            if (!value.startsWith("http://") && !value.startsWith("https://")) value = "https://" + value;
            server = value;
            prefs().edit().putString(KEY_SERVER, server).apply();
            showOffline(false);
            web.loadUrl(server + "/login");
        });
        box.addView(save, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)));
        return box;
    }

    private Button primaryButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setTextSize(16);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor("#1B3A6B"));
        bg.setCornerRadius(dp(12));
        b.setBackground(bg);
        return b;
    }

    private boolean isOnline() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        if (cm == null) return true;
        NetworkCapabilities caps = cm.getNetworkCapabilities(cm.getActiveNetwork());
        return caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    /** The saved briefs live in the phone; their page comes from the app's cache. */
    private void openSavedBriefs() {
        showOffline(false);
        web.getSettings().setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
        web.loadUrl(server + "/offline");
    }

    private boolean offlinePageWarm = false;

    /**
     * While online, quietly load the Saved for court page once so it (and its
     * scripts) are in the app's cache, ready for a court house with no signal.
     */
    private void warmOfflinePage() {
        if (offlinePageWarm || !isOnline()) return;
        offlinePageWarm = true;
        web.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        WebView warm = new WebView(this);
        warm.getSettings().setJavaScriptEnabled(true);
        warm.getSettings().setDomStorageEnabled(true);
        warm.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                view.postDelayed(view::destroy, 4000);
            }
        });
        warm.loadUrl(server + "/offline");
    }

    private void showOffline(boolean show) {
        offline.setVisibility(show ? View.VISIBLE : View.GONE);
    }

    // ------------------------------------------------------------- lifecycle

    @Override
    public void onBackPressed() {
        if (offline.getVisibility() == View.VISIBLE) {
            super.onBackPressed();
        } else if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
