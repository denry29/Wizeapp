import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Image,
  Linking,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  StatusBar,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { MaterialIcons } from "@react-native-vector-icons/material-icons/static";
import { useFonts } from "expo-font";
import * as FileSystem from "expo-file-system";
import * as ImagePicker from "expo-image-picker";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

const API_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  (Platform.OS === "web" ? "http://localhost:5000" : "http://192.168.100.37:5000");
const TAB_ITEMS = [
  ["Home", "home", "home"],
  ["Explore", "explore", "explore"],
  ["Favorites", "favorites", "favorite"],
  ["Trips", "trips", "luggage"],
  ["Profile", "profile", "person"],
];
const PROFILE_PHOTO_STORAGE_KEY = "wize.profile-photo";

function Button({ children, onPress, secondary = false, disabled = false, icon }) {
  return (
    <TouchableOpacity
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, secondary && styles.buttonSecondary, disabled && styles.disabled]}
    >
      {icon ? (
        <MaterialIcons
          name={icon}
          size={19}
          color={secondary ? "#126c91" : "#ffffff"}
          style={styles.buttonIcon}
        />
      ) : null}
      <Text style={[styles.buttonText, secondary && styles.buttonSecondaryText]}>
        {children}
      </Text>
    </TouchableOpacity>
  );
}

function Field({ label, value, onChangeText, placeholder, secureTextEntry, multiline, keyboardType, maxLength }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder || label}
        placeholderTextColor="#879493"
        secureTextEntry={secureTextEntry}
        multiline={multiline}
        keyboardType={keyboardType}
        maxLength={maxLength}
        style={[styles.input, multiline && styles.multiline]}
      />
    </View>
  );
}

function Card({ children, style }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

function WelcomeScreen({ height, onLogin, onRegister, onExplore, onSocialUnavailable }) {
  const introProgress = React.useRef(new Animated.Value(0)).current;
  const animationStarted = React.useRef(false);
  const animationInterval = React.useRef(null);
  const symbolWidth = 112;
  const loginMotion = (start) => ({
    opacity: introProgress.interpolate({
      inputRange: [start, Math.min(start + 0.06, 1)],
      outputRange: [0, 1],
      extrapolate: "clamp",
    }),
    transform: [{
      translateY: introProgress.interpolate({
        inputRange: [start, Math.min(start + 0.06, 1)],
        outputRange: [22, 0],
        extrapolate: "clamp",
      }),
    }],
  });

  const startAnimationOnLayout = () => {
    if (animationStarted.current) return;
    animationStarted.current = true;
    const startedAt = Date.now();
    const updateProgress = () => {
      const progress = Math.min((Date.now() - startedAt) / 8000, 1);
      introProgress.setValue(progress);
      if (progress >= 1 && animationInterval.current != null) {
        clearInterval(animationInterval.current);
        animationInterval.current = null;
      }
    };
    updateProgress();
    animationInterval.current = setInterval(updateProgress, 16);
  };

  useEffect(() => {
    const fallbackTimer = setTimeout(() => introProgress.setValue(1), 8300);
    startAnimationOnLayout();
    return () => {
      clearTimeout(fallbackTimer);
      if (animationInterval.current != null) {
        clearInterval(animationInterval.current);
        animationInterval.current = null;
      }
    };
  }, [introProgress]);

  const logoTranslateY = introProgress.interpolate({
    inputRange: [0, 0.58, 0.68],
    outputRange: [Math.max(0, (height - 182) / 2), Math.max(0, (height - 182) / 2), 0],
    extrapolate: "clamp",
  });
  const wordmarkOpacity = introProgress.interpolate({
    inputRange: [0.69, 0.78],
    outputRange: [0, 1],
    extrapolate: "clamp",
  });
  const wordmarkOffset = introProgress.interpolate({
    inputRange: [0.69, 0.78],
    outputRange: [8, 0],
    extrapolate: "clamp",
  });

  return (
    <View
      onLayout={startAnimationOnLayout}
      style={[styles.welcomeScreen, { minHeight: Math.max(height - 100, 620) }]}
    >
      <View style={styles.welcomeLogoStage}>
        <Animated.View
          style={[
            styles.welcomeLogoGroup,
            { transform: [{ translateY: logoTranslateY }] },
          ]}
        >
          <View style={styles.welcomeLogoClip}>
            <Animated.View
              style={{
                width: introProgress.interpolate({
                  inputRange: [0, 0.08],
                  outputRange: [0, symbolWidth],
                  extrapolate: "clamp",
                }),
                height: 94,
                overflow: "hidden",
              }}
            >
              <Image
                source={require("./static/logo-160.png")}
                style={styles.welcomeLogoImage}
                resizeMode="contain"
                accessibilityLabel="Wize logo"
              />
            </Animated.View>
          </View>
          <Animated.View
            style={{
              opacity: wordmarkOpacity,
              transform: [{ translateY: wordmarkOffset }],
            }}
          >
            
          </Animated.View>
        </Animated.View>
      </View>

      <Animated.View style={[styles.welcomeLoginContent, loginMotion(0.78)]}>
        <Text style={styles.welcomeLoginTitle}>Welcome to Wize</Text>
      </Animated.View>

      <Animated.View style={loginMotion(0.83)}>
        <View style={styles.welcomeOptionsGroup}>
      <View style={styles.welcomeSocialWrap}>
        <TouchableOpacity
          accessibilityRole="button"
          accessibilityLabel="Google sign-in is not configured"
          onPress={() => onSocialUnavailable("Google")}
          style={styles.welcomeSocialButton}
        >
          <Text style={styles.googleMark}>G</Text>
          <Text style={styles.welcomeSocialText}>Continue with Google</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.welcomeSocialWrap}>
        <TouchableOpacity
          accessibilityRole="button"
          accessibilityLabel="Facebook sign-in is not configured"
          onPress={() => onSocialUnavailable("Facebook")}
          style={styles.welcomeSocialButton}
        >
          <Text style={styles.facebookMark}>f</Text>
          <Text style={styles.welcomeSocialText}>Continue with Facebook</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.welcomeDivider}>
        <View style={styles.welcomeDividerLine} />
        <Text style={styles.welcomeDividerText}>or</Text>
        <View style={styles.welcomeDividerLine} />
      </View>

      <View style={styles.welcomeSocialWrap}>
        <TouchableOpacity
          accessibilityRole="button"
          onPress={onLogin}
          style={styles.welcomeEmailButton}
        >
          <MaterialIcons name="mail-outline" size={20} color="#ffffff" />
          <Text style={styles.welcomeEmailText}>Continue with Email</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.welcomeAccountActions}>
        <TouchableOpacity accessibilityRole="button" onPress={onLogin} style={styles.welcomeAccountAction}>
          <Text style={styles.welcomeAccountText}>Log In</Text>
        </TouchableOpacity>
        <View style={styles.welcomeAccountDivider} />
        <TouchableOpacity accessibilityRole="button" onPress={onRegister} style={styles.welcomeAccountAction}>
          <Text style={styles.welcomeAccountText}>Sign Up</Text>
        </TouchableOpacity>
      </View>

      <View>
        <TouchableOpacity
          accessibilityRole="button"
          onPress={onExplore}
          style={styles.welcomeExploreAction}
        >
          <MaterialIcons name="explore" size={17} color="#147998" />
          <Text style={styles.welcomeExploreText}>Explore destinations</Text>
        </TouchableOpacity>
        <Text style={styles.welcomeSocialNote}>
          Google and Facebook sign-in aren’t configured yet.
        </Text>
      </View>
        </View>
      </Animated.View>
    </View>
  );
}

function isRemoteImageUri(uri) {
  return typeof uri === "string"
    && /^https?:\/\/[a-z0-9.-]+(?::\d+)?(?:[/?#]|$)/i.test(uri);
}

function HotelPhoto({ uri, style }) {
  const validUri = isRemoteImageUri(uri);
  const [loading, setLoading] = useState(validUri);
  const [failed, setFailed] = useState(!validUri);

  useEffect(() => {
    setLoading(validUri);
    setFailed(!validUri);
  }, [uri, validUri]);

  if (failed || !validUri) {
    return (
      <View style={[style, styles.imageFallback]}>
        <MaterialIcons name="photo" size={30} color="#4d8ca4" />
        <Text style={styles.logoUnavailable}>Photo not available</Text>
      </View>
    );
  }

  return (
    <View style={[styles.hotelPhotoFrame, style]}>
      <Image
        source={{ uri }}
        style={styles.hotelPhotoImage}
        onLoad={() => setLoading(false)}
        onError={() => {
          setLoading(false);
          setFailed(true);
        }}
      />
      {loading && <ActivityIndicator color="#0877d8" style={styles.imageLoading} />}
    </View>
  );
}

function DestinationPhoto({ uri, destinationId, style }) {
  const validUri = isRemoteImageUri(uri) && uri.startsWith("https://");
  const [failed, setFailed] = useState(!validUri);
  const imageUri = validUri
    && destinationId
    && uri.startsWith("https://upload.wikimedia.org/")
    ? `${API_URL}/api/destinations/${destinationId}/image`
    : uri;

  useEffect(() => {
    setFailed(!validUri);
  }, [imageUri, validUri]);

  if (!validUri || failed) {
    return (
      <View style={[style, styles.imageFallback]}>
        <MaterialIcons name="photo" size={34} color="#4d8ca4" />
      </View>
    );
  }

  return (
    <Image
      source={{ uri: imageUri }}
      style={style}
      resizeMode="cover"
      onError={() => setFailed(true)}
    />
  );
}

function formatTravelDateTime(value) {
  if (!value) return "Not available";
  const [date, time] = value.split("T");
  return time ? `${date} · ${time.slice(0, 5)}` : value;
}

function formatTravelDuration(value) {
  if (!value) return "Not available";
  const match = /^PT(?:(\d+)H)?(?:(\d+)M)?$/.exec(value);
  if (!match) return value;
  const hours = match[1] ? `${match[1]}h` : "";
  const minutes = match[2] ? `${match[2]}m` : "";
  return [hours, minutes].filter(Boolean).join(" ") || value;
}

function formatPrice(amount, currency) {
  if (amount == null) return "Not available";
  return `${amount} ${currency || "Not available"}`;
}

function formatHotelPrice(amount, currency) {
  if (amount == null || !Number.isFinite(Number(amount))) return "Not available";
  return `${Number(amount).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency || "Not available"}`;
}

function displayHotelValue(value) {
  if (typeof value === "string" || typeof value === "number"
      || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function hotelStayNights(hotel) {
  const parseDate = (value) => {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const timestamp = Date.parse(`${value}T00:00:00Z`);
    if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== value) {
      return null;
    }
    return timestamp;
  };
  const checkIn = parseDate(hotel?.dates?.check_in);
  const checkOut = parseDate(hotel?.dates?.check_out);
  if (checkIn == null || checkOut == null || checkOut <= checkIn) return null;
  return (checkOut - checkIn) / 86400000;
}

function hotelEstimate(hotel) {
  const total = hotel.total_price == null || hotel.total_price === ""
    ? null
    : Number(hotel.total_price);
  if (Number.isFinite(total) && total >= 0) return total;

  const nightly = hotel.price_per_night == null || hotel.price_per_night === ""
    ? null
    : Number(hotel.price_per_night);
  const nights = hotelStayNights(hotel);
  if (!Number.isFinite(nightly) || nightly < 0 || nights == null) return null;
  return nightly * nights;
}

function hotelImageUris(hotel) {
  const images = Array.isArray(hotel.images) ? hotel.images : [];
  const urls = images.filter(isRemoteImageUri);
  if (!urls.length && isRemoteImageUri(hotel.image_url)) urls.push(hotel.image_url);
  return urls;
}

function App() {
  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  const [iconFontLoaded] = useFonts({
    MaterialIcons: require("@react-native-vector-icons/material-icons/fonts/MaterialIcons.ttf"),
    "MaterialIcons-Regular": require("@react-native-vector-icons/material-icons/fonts/MaterialIcons.ttf"),
  });
  const [screen, setScreen] = useState("welcome");
  const [authMode, setAuthMode] = useState("login");
  const [verificationEmail, setVerificationEmail] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  const [user, setUser] = useState(null);
  const [csrfToken, setCsrfToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [form, setForm] = useState({});
  const [search, setSearch] = useState("");
  const [homeSearchText, setHomeSearchText] = useState("");
  const [destinations, setDestinations] = useState([]);
  const [destinationPage, setDestinationPage] = useState(1);
  const [destinationPagination, setDestinationPagination] = useState(null);
  const [destinationsLoading, setDestinationsLoading] = useState(false);
  const [homeDestinations, setHomeDestinations] = useState([]);
  const [homeLoading, setHomeLoading] = useState(false);
  const [destinationFilters, setDestinationFilters] = useState({
    countries: [],
    categories: [],
  });
  const [showDestinationFilters, setShowDestinationFilters] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [destination, setDestination] = useState(null);
  const [favorites, setFavorites] = useState([]);
  const [trips, setTrips] = useState([]);
  const [trip, setTrip] = useState(null);
  const [tripDestinations, setTripDestinations] = useState([]);
  const [activities, setActivities] = useState([]);
  const [options, setOptions] = useState([]);
  const [hotelDateEdits, setHotelDateEdits] = useState({});
  const [selectedHotel, setSelectedHotel] = useState(null);
  const [hotelPhotoIndex, setHotelPhotoIndex] = useState(0);
  const [hotelReviews, setHotelReviews] = useState({
    items: [],
    loading: false,
    loaded: false,
    error: "",
  });
  const [expenses, setExpenses] = useState([]);
  const [budgetSummary, setBudgetSummary] = useState(null);
  const [checklists, setChecklists] = useState([]);
  const [notes, setNotes] = useState([]);
  const [profilePhoto, setProfilePhoto] = useState(null);
  const [profilePhotoBusy, setProfilePhotoBusy] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [searchKind, setSearchKind] = useState("");
  const [unavailableImages, setUnavailableImages] = useState({});
  const [editingNote, setEditingNote] = useState(null);
  const [editingChecklistItem, setEditingChecklistItem] = useState(null);

  const refreshCsrf = useCallback(async () => {
    if (!API_URL) {
      throw new Error(
        "Set EXPO_PUBLIC_API_URL to your computer's LAN address (currently http://192.168.100.37:5000) before starting Expo Go."
      );
    }
    const response = await fetch(`${API_URL}/api/auth/csrf`, {
      credentials: "include",
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Could not connect to TravelWise.");
    setCsrfToken(body.csrf_token);
    return body.csrf_token;
  }, []);

  const api = useCallback(
    async (path, options = {}) => {
      if (!API_URL) {
        throw new Error(
          "Set EXPO_PUBLIC_API_URL to your computer's LAN address (currently http://192.168.100.37:5000) before starting Expo Go."
        );
      }
      const method = (options.method || "GET").toUpperCase();
      const headers = { Accept: "application/json", ...options.headers };
      if (options.body && typeof options.body !== "string") {
        headers["Content-Type"] = "application/json";
      }
      if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
        const token = csrfToken || (await refreshCsrf());
        headers["X-CSRF-Token"] = token;
      }
      let response;
      try {
        response = await fetch(`${API_URL}${path}`, {
          ...options,
          method,
          headers,
          credentials: "include",
          body:
            options.body && typeof options.body !== "string"
              ? JSON.stringify(options.body)
              : options.body,
        });
      } catch (_networkError) {
        throw new Error(
          Platform.OS === "web"
            ? "Cannot reach Flask at http://localhost:5000. Start the backend and check the API URL."
            : "Cannot reach Flask at http://192.168.100.37:5000. Check the computer's LAN IP, firewall, and backend status."
        );
      }
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const requestError = new Error(body.error || `Request failed (${response.status}).`);
        requestError.code = body.code;
        requestError.email = body.email;
        requestError.retryAfter = body.retry_after;
        throw requestError;
      }
      return body;
    },
    [csrfToken, refreshCsrf]
  );

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        if (!API_URL) {
          throw new Error(
            "Set EXPO_PUBLIC_API_URL to your computer's LAN address (currently http://192.168.100.37:5000) before starting Expo Go."
          );
        }
        const csrfResponse = await fetch(`${API_URL}/api/auth/csrf`, {
          credentials: "include",
        });
        const csrf = await csrfResponse.json();
        if (!csrfResponse.ok) throw new Error("Flask API is unavailable.");
        if (mounted) setCsrfToken(csrf.csrf_token);
        const meResponse = await fetch(`${API_URL}/api/auth/me`, {
          credentials: "include",
        });
        if (meResponse.ok) {
          const me = await meResponse.json();
          if (mounted) {
            setUser(me.user);
            setScreen("home");
          }
        }
      } catch (connectionError) {
        if (mounted) setError(connectionError.message);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (resendCooldown <= 0) return undefined;
    const timer = setTimeout(
      () => setResendCooldown((seconds) => Math.max(0, seconds - 1)),
      1000
    );
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      if (screen === "explore") setDestinationsLoading(true);
      if (screen === "home") setHomeLoading(true);
      try {
        if (screen === "home") {
          const [destinationResult, tripResult] = await Promise.all([
            api("/api/destinations?per_page=8&page=1"),
            user ? api("/api/trips?per_page=100") : Promise.resolve({ trips: [] }),
          ]);
          if (mounted) {
            setHomeDestinations(destinationResult.destinations || []);
            setTrips(tripResult.trips || []);
          }
        } else if (screen === "explore") {
          const params = new URLSearchParams({
            per_page: "60",
            page: String(destinationPage),
          });
          if (search) params.set("search", search);
          if (selectedCountry) params.set("country", selectedCountry);
          if (selectedCategory) params.set("category", selectedCategory);
          const query = `?${params.toString()}`;
          const result = await api(`/api/destinations${query}`);
          if (mounted) {
            setDestinations((current) => (
              destinationPage === 1
                ? result.destinations || []
                : [...current, ...(result.destinations || [])]
            ));
            setDestinationPagination(result.pagination || null);
          }
        } else if (screen === "destination" && destination?.destination_id) {
          const result = await api(`/api/destinations/${destination.destination_id}`);
          if (mounted) setDestination(result.destination);
        } else if (screen === "favorites" && user) {
          const result = await api("/api/favorites");
          if (mounted) setFavorites(result.favorites || []);
        } else if (screen === "trips" && user) {
          const result = await api("/api/trips?per_page=100");
          if (mounted) setTrips(result.trips || []);
        } else if (screen === "trip" && trip?.trip_id) {
          const [detail, places, schedule, saved, summary, expenseList] = await Promise.all([
            api(`/api/trips/${trip.trip_id}`),
            api(`/api/trips/${trip.trip_id}/destinations`),
            api(`/api/trips/${trip.trip_id}/schedules`),
            api(`/api/trips/${trip.trip_id}/saved-options`),
            api(`/api/trips/${trip.trip_id}/expenses/summary`),
            api(`/api/trips/${trip.trip_id}/expenses`),
          ]);
          if (mounted) {
            setTrip(detail.trip);
            setTripDestinations(places.destinations || []);
            setActivities(schedule.schedules || []);
            setOptions(saved.options || []);
            setBudgetSummary(summary);
            setExpenses(expenseList.expenses || []);
          }
        } else if ((screen === "budget" || screen === "expenses") && trip?.trip_id) {
          const [summary, list] = await Promise.all([
            api(`/api/trips/${trip.trip_id}/expenses/summary`),
            api(`/api/trips/${trip.trip_id}/expenses`),
          ]);
          if (mounted) {
            setBudgetSummary(summary);
            setExpenses(list.expenses || []);
          }
        } else if (screen === "checklist" && trip?.trip_id) {
          const result = await api(`/api/trips/${trip.trip_id}/checklists`);
          if (mounted) setChecklists(result.checklists || []);
        } else if (screen === "notes" && trip?.trip_id) {
          const result = await api(`/api/trips/${trip.trip_id}/notes`);
          if (mounted) setNotes(result.notes || []);
        }
      } catch (loadError) {
        if (mounted) setError(loadError.message);
      } finally {
        if (mounted && screen === "explore") setDestinationsLoading(false);
        if (mounted && screen === "home") setHomeLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [api, destination?.destination_id, destinationPage, refreshKey, screen, search, selectedCategory, selectedCountry, trip?.trip_id, user]);

  useEffect(() => {
    if (screen !== "explore" || destinationFilters.countries.length) return undefined;
    let mounted = true;
    api("/api/destinations/filters")
      .then((result) => {
        if (mounted) {
          setDestinationFilters({
            countries: result.countries || [],
            categories: result.categories || [],
          });
        }
      })
      .catch((filterError) => {
        if (mounted) setError(filterError.message);
      });
    return () => {
      mounted = false;
    };
  }, [api, destinationFilters.countries.length, screen]);

  useEffect(() => {
    let mounted = true;
    async function loadProfilePhoto() {
      if (!user?.user_id) {
        setProfilePhoto(null);
        return;
      }
      try {
        const storedUri = await AsyncStorage.getItem(
          `${PROFILE_PHOTO_STORAGE_KEY}:${user.user_id}`
        );
        if (!mounted || !storedUri) return;
        if (Platform.OS === "web" || new FileSystem.File(storedUri).exists) {
          setProfilePhoto(storedUri);
        } else {
          await AsyncStorage.removeItem(
            `${PROFILE_PHOTO_STORAGE_KEY}:${user.user_id}`
          );
          setProfilePhoto(null);
        }
      } catch (storageError) {
        if (mounted) setError(`Profile photo could not be loaded: ${storageError.message}`);
      }
    }
    loadProfilePhoto();
    return () => {
      mounted = false;
    };
  }, [user?.user_id]);

  const change = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  const resetForm = () => setForm({});
  const act = async (operation, successMessage) => {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await operation();
      if (successMessage) setNotice(successMessage);
      setRefreshKey((value) => value + 1);
      return true;
    } catch (actionError) {
      if (actionError.code === "email_not_verified" && actionError.email) {
        setVerificationEmail(actionError.email);
        setVerificationCode("");
        setScreen("verifyEmail");
      } else if (actionError.code === "email_delivery_unavailable" && actionError.email) {
        setVerificationEmail(actionError.email);
        setVerificationCode("");
        setScreen("verifyEmail");
      }
      if (actionError.retryAfter) {
        setResendCooldown(Number(actionError.retryAfter));
      }
      setError(actionError.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  async function submitAuth() {
    if (authMode === "register") {
      await act(async () => {
        const result = await api("/api/auth/register", {
          method: "POST",
          body: {
            full_name: form.full_name,
            email: form.email,
            password: form.password,
            confirm_password: form.confirm_password,
          },
        });
        setVerificationEmail(result.email);
        setVerificationCode("");
        setResendCooldown(60);
        setScreen("verifyEmail");
        change("email", result.email);
        change("password", "");
        change("confirm_password", "");
      }, "Check your inbox for the 6-digit verification code.");
      return;
    }
    await act(async () => {
      const result = await api("/api/auth/login", {
        method: "POST",
        body: { email: form.email, password: form.password },
      });
      setUser(result.user);
      await refreshCsrf();
      setScreen("home");
      resetForm();
      if (result.notification_warning) setNotice(result.notification_warning);
    }, "You are signed in.");
  }

  async function submitEmailVerification() {
    await act(async () => {
      await api("/api/auth/verify-email", {
        method: "POST",
        body: { email: verificationEmail, code: verificationCode },
      });
      setAuthMode("login");
      setVerificationCode("");
      change("email", verificationEmail);
      change("password", "");
      setScreen("auth");
    }, "Email verified. Sign in to continue.");
  }

  async function resendVerificationCode() {
    await act(async () => {
      await api("/api/auth/resend-verification", {
        method: "POST",
        body: { email: verificationEmail },
      });
      setResendCooldown(60);
    }, "If this address has a pending account, a new code was sent.");
  }

  async function submitTrip() {
    const result = await api("/api/trips", {
      method: "POST",
      body: {
        trip_name: form.trip_name,
        start_date: form.start_date,
        end_date: form.end_date,
        description: form.description || "",
        budget: form.budget ? Number(form.budget) : null,
        budget_currency: form.budget_currency || "PHP",
      },
    });
    setTrip(result.trip);
    resetForm();
    setScreen("trip");
  }

  async function searchHotels() {
    setSearchResults([]);
    setSearchKind("");
    setUnavailableImages({});
    const params = new URLSearchParams({
      city: form.city || "",
      country: (form.hotel_country || "JP").toUpperCase(),
      check_in: form.check_in || trip.start_date || "",
      check_out: form.check_out || trip.end_date || "",
      adults: form.hotel_adults || "2",
      rooms: form.hotel_rooms || "1",
      children: form.hotel_children || "0",
      child_ages: form.hotel_child_ages || "",
    });
    const currency = form.hotel_currency || trip.budget_currency;
    if (currency) params.set("currency", currency.toUpperCase());
    let result;
    try {
      result = await api(`/api/hotels/search?${params.toString()}`, {
        cache: "no-store",
      });
    } catch (searchError) {
      throw new Error(`No results available right now. Please try again. ${searchError.message}`);
    }
    const searchCriteria = {
      adults: Number(params.get("adults")),
      children: Number(params.get("children")),
      rooms: Number(params.get("rooms")),
    };
    setSearchResults((result.hotels || []).map((hotel) => ({
      ...hotel,
      search_criteria: searchCriteria,
      searched_at: result.searched_at,
    })));
    setSearchKind("hotel");
  }

  async function saveOption(kind, result) {
    const title =
      kind === "flight"
        ? `${result.airline} ${result.flight_number}: ${result.origin} → ${result.destination}`
        : result.name;
    const calculatedAmount = kind === "flight" ? result.price : hotelEstimate(result);
    const amount = kind === "hotel" && !result.currency
      ? null
      : calculatedAmount;
    const saved = await act(
      () =>
        api(`/api/trips/${trip.trip_id}/saved-options`, {
          method: "POST",
          body: {
            option_type: kind,
            title,
            amount: amount == null ? null : Number(amount),
            currency: amount == null ? null : result.currency || null,
            details: result,
          },
        }),
      "Added to trip. No purchase or booking was made."
    );
    if (saved && kind === "hotel") setScreen("trip");
  }

  async function loadHotelReviews(hotel) {
    setHotelReviews((current) => ({ ...current, loading: true, error: "" }));
    try {
        const params = new URLSearchParams({
          platform: hotel.provider,
          listing_id: hotel.platform_listing_id,
        });
        const result = await api(`/api/hotels/reviews?${params.toString()}`);
        setHotelReviews({
          items: Array.isArray(result.reviews) ? result.reviews : [],
          loading: false,
          loaded: true,
          error: "",
        });
    } catch (reviewError) {
        setHotelReviews((current) => ({
          ...current,
          loading: false,
          error: reviewError.message,
        }));
    }
  }

  async function updateHotelDates(option) {
    const details = option.details || {};
    const originalDates = details.dates || {};
    const edits = hotelDateEdits[option.option_id] || {};
    await act(async () => {
      await api(`/api/saved-options/${option.option_id}`, {
        method: "PATCH",
        body: {
          check_in: edits.check_in ?? originalDates.check_in ?? "",
          check_out: edits.check_out ?? originalDates.check_out ?? "",
        },
      });
      setHotelDateEdits((current) => {
        const updated = { ...current };
        delete updated[option.option_id];
        return updated;
      });
    }, "Hotel dates and estimated cost updated.");
  }

  function requireUser(next) {
    if (!user) {
      setAuthMode("login");
      setScreen("auth");
      return;
    }
    next();
  }

  function openTrip(value) {
    requireUser(() => {
      setTrip(value);
      setScreen("trip");
    });
  }

  async function chooseProfilePhoto() {
    if (!user?.user_id || profilePhotoBusy) return;
    setProfilePhotoBusy(true);
    setError("");
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        throw new Error("Allow photo access to choose a profile picture.");
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.85,
      });
      const asset = result.canceled ? null : result.assets?.[0];
      if (!asset?.uri) return;

      let savedUri = asset.uri;
      if (Platform.OS !== "web") {
        const photoDirectory = new FileSystem.Directory(
          FileSystem.Paths.document,
          "profile-photos"
        );
        if (!photoDirectory.exists) {
          photoDirectory.create({ idempotent: true, intermediates: true });
        }
        const fileExtension = asset.fileName?.split(".").pop()?.toLowerCase()
          || (asset.mimeType === "image/png" ? "png" : "jpg");
        const profileFile = new FileSystem.File(
          photoDirectory,
          `profile-${user.user_id}-${Date.now()}.${fileExtension}`
        );
        await new FileSystem.File(asset.uri).copy(profileFile);
        savedUri = profileFile.uri;
      }
      await AsyncStorage.setItem(
        `${PROFILE_PHOTO_STORAGE_KEY}:${user.user_id}`,
        savedUri
      );
      setProfilePhoto(savedUri);
    } catch (photoError) {
      setError(photoError.message || "Could not save the profile picture.");
    } finally {
      setProfilePhotoBusy(false);
    }
  }

  async function removeProfilePhoto() {
    if (!user?.user_id) return;
    setProfilePhotoBusy(true);
    try {
      if (profilePhoto && Platform.OS !== "web") {
        const photoFile = new FileSystem.File(profilePhoto);
        if (photoFile.exists) photoFile.delete();
      }
      await AsyncStorage.removeItem(
        `${PROFILE_PHOTO_STORAGE_KEY}:${user.user_id}`
      );
      setProfilePhoto(null);
    } catch (photoError) {
      setError(photoError.message || "Could not remove the profile picture.");
    } finally {
      setProfilePhotoBusy(false);
    }
  }

  async function openTravelSearch(target) {
    if (!user) {
      setAuthMode("login");
      setScreen("auth");
      return;
    }
    await act(async () => {
      const result = await api("/api/trips?per_page=100");
      const availableTrips = result.trips || [];
      setTrips(availableTrips);
      if (!availableTrips.length) {
        setScreen("trips");
        setNotice("Create a trip before searching and saving hotels.");
        return;
      }
      setTrip(availableTrips.find((item) => item.trip_id === trip?.trip_id) || availableTrips[0]);
      setSearchResults([]);
      setSearchKind("");
      resetForm();
      setScreen(target);
    });
  }

  function renderDestinationCard(item, removable = false) {
    const cardWidth = windowWidth < 600
      ? Math.max(0, windowWidth - 40)
      : undefined;
    return (
      <View
        key={item.destination_id}
        style={[styles.destinationCardWrap, cardWidth ? { width: cardWidth } : null]}
      >
        <TouchableOpacity
          accessibilityRole="button"
          onPress={() => {
            setDestination(item);
            setScreen("destination");
          }}
          style={[styles.destinationCard, cardWidth ? { width: cardWidth } : null]}
        >
          <DestinationPhoto
            key={item.image_url || `destination-${item.destination_id}-no-photo`}
            uri={item.image_url}
            destinationId={item.destination_id}
            style={styles.destinationImage}
          />
          <View style={styles.destinationInfo}>
            <Text numberOfLines={1} style={styles.cardTitle}>{item.name}</Text>
            <View style={styles.inlineMeta}>
              <MaterialIcons name="location-on" size={15} color="#52758a" />
              <Text numberOfLines={1} style={styles.muted}>
                {[item.city, item.country].filter(Boolean).join(", ")}
              </Text>
            </View>
            <Text numberOfLines={2} style={styles.cardDescription}>{item.description}</Text>
          </View>
        </TouchableOpacity>
        {removable ? (
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel={`Remove ${item.name} from favorites`}
            onPress={() => act(
              () => api(`/api/favorites/${item.destination_id}`, { method: "DELETE" }),
              "Favorite removed."
            )}
            style={styles.favoriteRemove}
          >
            <MaterialIcons name="favorite" size={20} color="#d64e62" />
          </TouchableOpacity>
        ) : null}
      </View>
    );
  }

  function renderWideDestinationCard(item) {
    const width = Math.min(Math.max(windowWidth * 0.68, 220), 270);
    return (
      <TouchableOpacity
        key={item.destination_id}
        accessibilityRole="button"
        onPress={() => {
          setDestination(item);
          setScreen("destination");
        }}
        style={[styles.wideDestinationCard, { width }]}
      >
        <DestinationPhoto
          uri={item.image_url}
          destinationId={item.destination_id}
          style={styles.wideDestinationImage}
        />
        <View style={styles.wideCardInfo}>
          <Text numberOfLines={1} style={styles.cardTitle}>{item.name}</Text>
          <View style={styles.inlineMeta}>
            <MaterialIcons name="location-on" size={15} color="#52758a" />
            <Text numberOfLines={1} style={styles.muted}>
              {[item.city, item.country].filter(Boolean).join(", ")}
            </Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  }

  function renderHomeScreen() {
    const hotelResults = searchKind === "hotel" ? searchResults : [];
    return (
      <View style={styles.homeScreen}>
        <View style={styles.greetingRow}>
          <View style={styles.greetingCopy}>
            <Text style={styles.eyebrow}>YOUR NEXT JOURNEY STARTS HERE</Text>
            <Text numberOfLines={1} style={styles.homeGreeting}>
              {user?.full_name ? `Hello, ${user.full_name.split(" ")[0]}` : "Hello, traveler"}
            </Text>
            
          </View>
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel="View login alert information"
            onPress={() => setScreen("profile")}
            style={styles.notificationButton}
          >
            <MaterialIcons name="notifications-none" size={22} color="#456574" />
          </TouchableOpacity>
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel="Open profile"
            onPress={() => setScreen(user ? "profile" : "auth")}
            style={styles.avatarButton}
          >
            {profilePhoto ? (
              <Image source={{ uri: profilePhoto }} style={styles.greetingAvatar} />
            ) : (
              <MaterialIcons name="person" size={25} color="#16728f" />
            )}
          </TouchableOpacity>
        </View>

        <View style={styles.homeSearchCard}>
          <MaterialIcons name="search" size={23} color="#568094" />
          <TextInput
            accessibilityLabel="Search destinations"
            value={homeSearchText}
            onChangeText={setHomeSearchText}
            onSubmitEditing={() => {
              setSearch(homeSearchText.trim());
              setSelectedCountry("");
              setSelectedCategory("");
              setDestinationPage(1);
              setScreen("explore");
            }}
            placeholder="Where do you want to go?"
            placeholderTextColor="#718b99"
            returnKeyType="search"
            style={styles.homeSearchInput}
          />
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel="Search destinations"
            onPress={() => {
              setSearch(homeSearchText.trim());
              setSelectedCountry("");
              setSelectedCategory("");
              setDestinationPage(1);
              setScreen("explore");
            }}
            style={styles.searchSubmit}
          >
            <MaterialIcons name="arrow-forward" size={20} color="#ffffff" />
          </TouchableOpacity>
        </View>

        <View style={styles.homeSection}>
          <View style={styles.sectionHeadingRow}>
            <View>
              <Text style={styles.homeSectionTitle}>Explore destinations</Text>
              <Text style={styles.homeSectionSubtitle}>Real places across Asia</Text>
            </View>
            <TouchableOpacity
              accessibilityRole="button"
              onPress={() => {
                setSearch("");
                setDestinationPage(1);
                setScreen("explore");
              }}
              style={styles.sectionAction}
            >
              <Text style={styles.sectionActionText}>See all</Text>
              <MaterialIcons name="arrow-forward" size={16} color="#147998" />
            </TouchableOpacity>
          </View>
          {homeLoading && !homeDestinations.length ? (
            <ActivityIndicator color="#147998" style={styles.sectionLoader} />
          ) : homeDestinations.length ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.horizontalCards}>
              {homeDestinations.slice(0, 5).map(renderWideDestinationCard)}
            </ScrollView>
          ) : (
            <Text style={styles.muted}>Destinations are temporarily unavailable.</Text>
          )}
        </View>

        <View style={styles.homeSection}>
          <View style={styles.sectionHeadingRow}>
            <View>
              <Text style={styles.homeSectionTitle}>Featured hotels</Text>
              <Text style={styles.homeSectionSubtitle}>
                {hotelResults.length ? "From your latest live search" : "Check live availability for your dates"}
              </Text>
            </View>
            <MaterialIcons name="hotel" size={23} color="#147998" />
          </View>
          {hotelResults.length ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.horizontalCards}>
              {hotelResults.slice(0, 5).map((hotel, index) => (
                <TouchableOpacity
                  key={`${hotel.hotel_id || hotel.name}-${index}`}
                  accessibilityRole="button"
                  onPress={() => {
                    setSelectedHotel(hotel);
                    setHotelPhotoIndex(0);
                    setHotelReviews({ items: [], loading: false, loaded: false, error: "" });
                    setScreen("hotelDetails");
                  }}
                  style={[styles.featuredHotelCard, { width: Math.min(windowWidth * 0.72, 290) }]}
                >
                  <HotelPhoto uri={hotelImageUris(hotel)[0]} style={styles.featuredHotelImage} />
                  <View style={styles.wideCardInfo}>
                    <Text numberOfLines={1} style={styles.cardTitle}>{hotel.name || "Hotel"}</Text>
                    <View style={styles.inlineMeta}>
                      <MaterialIcons name="location-on" size={15} color="#52758a" />
                      <Text numberOfLines={1} style={styles.muted}>
                        {[hotel.location?.city, hotel.location?.country].filter(Boolean).join(", ")
                          || hotel.location?.city_code || "Location not available"}
                      </Text>
                    </View>
                    {hotel.rating != null && (
                      <View style={styles.inlineMeta}>
                        <MaterialIcons name="star" size={16} color="#d99624" />
                        <Text style={styles.ratingCompact}>{hotel.rating}</Text>
                      </View>
                    )}
                    <Text numberOfLines={1} style={styles.hotelCardPrice}>
                      {hotel.price_per_night != null
                        ? `${formatHotelPrice(hotel.price_per_night, hotel.currency)} / night`
                        : hotel.total_price != null
                          ? `${formatHotelPrice(hotel.total_price, hotel.currency)} total`
                          : "Price not available"}
                    </Text>
                  </View>
                </TouchableOpacity>
              ))}
            </ScrollView>
          ) : (
            <Card style={styles.featuredHotelEmpty}>
              <MaterialIcons name="hotel" size={26} color="#147998" />
              <View style={styles.emptyCopy}>
                <Text style={styles.cardTitle}>Search live hotel availability</Text>
                <Text style={styles.muted}>Choose a trip and dates to see current offers.</Text>
              </View>
              <Button icon="search" onPress={() => openTravelSearch("hotels")}>Search hotels</Button>
            </Card>
          )}
        </View>

        <View style={styles.homeSection}>
          <View style={styles.sectionHeadingRow}>
            <View>
              <Text style={styles.homeSectionTitle}>Upcoming trips</Text>
              <Text style={styles.homeSectionSubtitle}>Your plans, all in one place</Text>
            </View>
            <MaterialIcons name="luggage" size={23} color="#147998" />
          </View>
          {!user ? (
            <Card style={styles.emptyCard}>
              <MaterialIcons name="person-outline" size={27} color="#147998" />
              <Text style={styles.cardTitle}>Sign in to see your trips</Text>
              <Button secondary icon="login" onPress={() => { setAuthMode("login"); setScreen("auth"); }}>
                Sign in
              </Button>
            </Card>
          ) : trips.length ? (
            <View style={styles.homeTripList}>
              {trips.slice(0, 3).map((item) => (
                <TouchableOpacity
                  key={item.trip_id}
                  accessibilityRole="button"
                  onPress={() => openTrip(item)}
                  style={styles.homeTripCard}
                >
                  <View style={styles.tripIconWrap}>
                    <MaterialIcons name="luggage" size={21} color="#147998" />
                  </View>
                  <View style={styles.homeTripCopy}>
                    <Text numberOfLines={1} style={styles.cardTitle}>{item.trip_name}</Text>
                    <View style={styles.inlineMeta}>
                      <MaterialIcons name="calendar-today" size={15} color="#668494" />
                      <Text numberOfLines={1} style={styles.muted}>
                        {item.start_date} – {item.end_date}
                      </Text>
                    </View>
                  </View>
                  <MaterialIcons name="arrow-forward" size={19} color="#668494" />
                </TouchableOpacity>
              ))}
              <Button secondary icon="add" onPress={() => { resetForm(); setScreen("createTrip"); }}>
                Plan a trip
              </Button>
            </View>
          ) : (
            <Card style={styles.emptyCard}>
              <MaterialIcons name="luggage" size={28} color="#147998" />
              <View style={styles.emptyCopy}>
                <Text style={styles.cardTitle}>No trips yet</Text>
                <Text style={styles.muted}>Create a trip to start collecting your plans.</Text>
              </View>
              <Button icon="add" onPress={() => { resetForm(); setScreen("createTrip"); }}>
                Create a trip
              </Button>
            </Card>
          )}
        </View>
      </View>
    );
  }

  function renderTripFeatures() {
    return (
      <View style={styles.featureGrid}>
        {[
          ["Hotels", "hotels"],
          ["Budget", "budget"],
          ["Expenses", "expenses"],
          ["Checklist", "checklist"],
          ["Notes", "notes"],
        ].map(([label, page]) => (
          <Button key={page} secondary onPress={() => setScreen(page)}>{label}</Button>
        ))}
      </View>
    );
  }

  function renderScreen() {
    if (screen === "home") return renderHomeScreen();

    if (screen === "welcome") {
      return (
        <WelcomeScreen
          height={windowHeight}
          onLogin={() => { setAuthMode("login"); setError(""); setScreen("auth"); }}
          onRegister={() => { setAuthMode("register"); setError(""); setScreen("auth"); }}
          onExplore={() => setScreen("explore")}
          onSocialUnavailable={(provider) => {
            setError(`${provider} sign-in is not configured yet. Continue with email instead.`);
          }}
        />
      );
    }

    if (screen === "auth") {
      return (
        <Card style={styles.formCard}>
          <Text style={styles.sectionTitle}>{authMode === "login" ? "Welcome back" : "Create your account"}</Text>
          {authMode === "register" && (
            <Field label="Full name" value={form.full_name || ""} onChangeText={(value) => change("full_name", value)} />
          )}
          <Field label="Email" value={form.email || ""} onChangeText={(value) => change("email", value)} keyboardType="email-address" />
          <Field label="Password" value={form.password || ""} onChangeText={(value) => change("password", value)} secureTextEntry />
          {authMode === "register" && (
            <Field label="Confirm password" value={form.confirm_password || ""} onChangeText={(value) => change("confirm_password", value)} secureTextEntry />
          )}
          <Button disabled={busy} onPress={submitAuth}>{authMode === "login" ? "Sign in" : "Create account"}</Button>
          <Button secondary onPress={() => setAuthMode(authMode === "login" ? "register" : "login")}>
            {authMode === "login" ? "New to TravelWise? Register" : "Already have an account? Sign in"}
          </Button>
        </Card>
      );
    }

    if (screen === "verifyEmail") {
      return (
        <Card style={styles.formCard}>
          <Text style={styles.sectionTitle}>Verify your email</Text>
          <Text style={styles.bodyText}>Enter the 6-digit code sent to:</Text>
          <Text style={styles.cardTitle}>{verificationEmail || "your email address"}</Text>
          <Field
            label="Verification code"
            value={verificationCode}
            onChangeText={(value) => setVerificationCode(value.replace(/\D/g, ""))}
            placeholder="000000"
            keyboardType="number-pad"
            maxLength={6}
          />
          <Button
            disabled={busy || verificationCode.length !== 6}
            onPress={submitEmailVerification}
          >
            Verify email
          </Button>
          <Button
            secondary
            disabled={busy || resendCooldown > 0}
            onPress={resendVerificationCode}
          >
            {resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : "Resend code"}
          </Button>
          <Button secondary onPress={() => { setAuthMode("login"); setScreen("auth"); }}>
            Back to sign in
          </Button>
        </Card>
      );
    }

    if (screen === "explore") {
      return (
        <View style={styles.screenSection}>
          <Text style={styles.eyebrow}>ASIA, YOUR WAY</Text>
          <Text style={styles.screenTitle}>Explore destinations</Text>
          <View style={styles.exploreSearchRow}>
            <View style={styles.exploreSearchBox}>
              <MaterialIcons name="search" size={21} color="#638292" />
              <TextInput
                accessibilityLabel="Search destinations by name, city, or description"
                value={search}
                onChangeText={(value) => {
                  setSearch(value);
                  setDestinationPage(1);
                  setDestinationPagination(null);
                }}
                placeholder="Search places"
                placeholderTextColor="#718b99"
                returnKeyType="search"
                style={styles.exploreSearchInput}
              />
            </View>
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel={showDestinationFilters ? "Hide filters" : "Show filters"}
              onPress={() => setShowDestinationFilters((shown) => !shown)}
              style={[styles.filterButton, showDestinationFilters && styles.filterButtonActive]}
            >
              <MaterialIcons name="filter-list" size={22} color="#147998" />
            </TouchableOpacity>
          </View>
          {showDestinationFilters && (
            <View style={styles.filterPanel}>
              <Text style={styles.filterLabel}>Country</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.filterChoices}>
                {["", ...destinationFilters.countries].map((country) => (
                  <TouchableOpacity
                    key={country || "all-countries"}
                    onPress={() => {
                      setSelectedCountry(country);
                      setDestinationPage(1);
                      setDestinationPagination(null);
                    }}
                    style={[styles.filterChip, selectedCountry === country && styles.filterChipActive]}
                  >
                    <Text style={[styles.filterChipText, selectedCountry === country && styles.filterChipTextActive]}>
                      {country || "All"}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
              <Text style={styles.filterLabel}>Category</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.filterChoices}>
                {["", ...destinationFilters.categories].map((category) => (
                  <TouchableOpacity
                    key={category || "all-categories"}
                    onPress={() => {
                      setSelectedCategory(category);
                      setDestinationPage(1);
                      setDestinationPagination(null);
                    }}
                    style={[styles.filterChip, selectedCategory === category && styles.filterChipActive]}
                  >
                    <Text style={[styles.filterChipText, selectedCategory === category && styles.filterChipTextActive]}>
                      {category ? category.replaceAll("_", " ") : "All"}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          )}
          <Text style={styles.resultsCount}>
            {destinationPagination?.total ?? "Browse"} places
          </Text>
          <View style={styles.destinationGrid}>
            {destinations.map((item) => renderDestinationCard(item))}
          </View>
          {destinationsLoading && !destinations.length && (
            <ActivityIndicator color="#147998" style={styles.sectionLoader} />
          )}
          {!destinationsLoading && !destinations.length && (
            <View style={styles.emptyCard}>
              <MaterialIcons name="search-off" size={30} color="#147998" />
              <Text style={styles.cardTitle}>No destinations found</Text>
              <Text style={styles.muted}>Try another search or clear your filters.</Text>
            </View>
          )}
          {destinationPagination?.has_next && (
            <Button
              disabled={destinationsLoading}
              icon="expand-more"
              onPress={() => setDestinationPage((page) => page + 1)}
            >
              {destinationsLoading ? "Loading destinations…" : "Load more destinations"}
            </Button>
          )}
        </View>
      );
    }

    if (screen === "destination" && destination) {
      return (
        <View style={styles.screenSection}>
          <TouchableOpacity accessibilityRole="button" onPress={() => setScreen("explore")}
            style={styles.backLink}>
            <MaterialIcons name="arrow-back" size={19} color="#147998" />
            <Text style={styles.backLinkText}>Explore</Text>
          </TouchableOpacity>
          <DestinationPhoto
            key={destination.image_url || `destination-${destination.destination_id}-no-photo`}
            uri={destination.image_url}
            destinationId={destination.destination_id}
            style={styles.detailImage}
          />
          <View style={styles.inlineMeta}>
            <MaterialIcons name="location-on" size={16} color="#52758a" />
            <Text style={styles.muted}>{[destination.city, destination.country].filter(Boolean).join(", ")}</Text>
          </View>
          <Text style={styles.screenTitle}>{destination.name}</Text>
          <Text style={styles.bodyText}>{destination.description}</Text>
          <View style={styles.detailGrid}>
            <Card><Text style={styles.label}>Category</Text><Text>{(destination.category || "").replaceAll("_", " ")}</Text></Card>
            <Card><Text style={styles.label}>Entry fee</Text><Text>{destination.estimated_entrance_fee == null ? "Not available" : `${destination.estimated_entrance_fee} ${destination.currency || ""}`}</Text></Card>
            <Card><Text style={styles.label}>Best time to visit</Text><Text>{destination.best_time_to_visit || "Not available"}</Text></Card>
            <Card><Text style={styles.label}>Suggested duration</Text><Text>{destination.recommended_duration || "Not available"}</Text></Card>
          </View>
          {destination.image_attribution && (
            <Text
              accessibilityRole="link"
              style={styles.attribution}
              onPress={() => destination.image_source_url && Linking.openURL(destination.image_source_url)}
            >
              Photo: {destination.image_attribution} · {destination.image_license} (view source)
            </Text>
          )}
          <View style={styles.actions}>
            <Button icon="favorite" onPress={() => requireUser(async () => {
              await act(() => api(`/api/favorites/${destination.destination_id}`, { method: "POST" }), "Saved to favorites.");
            })}>Save favorite</Button>
            <Button secondary icon="add" onPress={() => requireUser(async () => {
              await act(async () => {
                const result = await api("/api/trips?per_page=100");
                setTrips(result.trips || []);
                setScreen("trips");
              });
            })}>Add to a trip</Button>
          </View>
          <Text style={styles.safetyNote}>You can add this destination to a trip plan. No travel is booked.</Text>
        </View>
      );
    }

    if (screen === "favorites") {
      return (
        <View style={styles.screenSection}>
          <Text style={styles.eyebrow}>YOUR SHORTLIST</Text>
          <Text style={styles.screenTitle}>Favorites</Text>
          {user ? (
            favorites.length ? (
              <View style={styles.destinationGrid}>
                {favorites.map((item) => renderDestinationCard(item, true))}
              </View>
            ) : (
              <View style={styles.emptyCard}>
                <MaterialIcons name="favorite-border" size={32} color="#147998" />
                <Text style={styles.cardTitle}>Your shortlist is empty</Text>
                <Text style={styles.muted}>Save places you love and they’ll appear here.</Text>
                <Button secondary icon="explore" onPress={() => setScreen("explore")}>
                  Explore destinations
                </Button>
              </View>
            )
          ) : (
            <View style={styles.emptyCard}>
              <MaterialIcons name="favorite-border" size={32} color="#147998" />
              <Text style={styles.cardTitle}>Sign in to see your favorites</Text>
              <Button onPress={() => { setAuthMode("login"); setScreen("auth"); }}>Sign in</Button>
            </View>
          )}
        </View>
      );
    }

    if (screen === "trips") {
      return (
        <View style={styles.screenSection}>
          <Text style={styles.eyebrow}>YOUR TRAVEL PLANS</Text>
          <Text style={styles.screenTitle}>My trips</Text>
          {user ? (
            <>
              <Button icon="add" onPress={() => { resetForm(); setScreen("createTrip"); }}>
                Create a trip
              </Button>
              <View style={styles.tripList}>
                {trips.map((item) => (
                  <TouchableOpacity
                    key={item.trip_id}
                    accessibilityRole="button"
                    onPress={() => openTrip(item)}
                    style={styles.tripListCard}
                  >
                    <View style={styles.tripIconWrap}>
                      <MaterialIcons name="luggage" size={22} color="#147998" />
                    </View>
                    <View style={styles.tripListCopy}>
                      <Text numberOfLines={1} style={styles.cardTitle}>{item.trip_name}</Text>
                      <View style={styles.inlineMeta}>
                        <MaterialIcons name="calendar-today" size={15} color="#668494" />
                        <Text style={styles.muted}>{item.start_date} – {item.end_date}</Text>
                      </View>
                      <Text numberOfLines={1} style={styles.muted}>
                        {item.budget ? `${item.budget} ${item.budget_currency || ""} budget` : "Budget not set"}
                      </Text>
                    </View>
                    <MaterialIcons name="arrow-forward" size={20} color="#668494" />
                  </TouchableOpacity>
                ))}
              </View>
              {!trips.length && (
                <View style={styles.emptyCard}>
                  <MaterialIcons name="luggage" size={32} color="#147998" />
                  <Text style={styles.cardTitle}>Your first trip starts here</Text>
                  <Text style={styles.muted}>Create a plan to organize places, stays and expenses.</Text>
                  <Button icon="add" onPress={() => { resetForm(); setScreen("createTrip"); }}>
                    Create a trip
                  </Button>
                </View>
              )}
              {destination && trips.length > 0 && (
                <View style={styles.destinationTripPicker}>
                  <Text style={styles.homeSectionTitle}>Add {destination.name} to a trip</Text>
                  {trips.map((item) => (
                    <Button key={`add-${item.trip_id}`} secondary icon="add"
                      onPress={() => act(async () => {
                        await api(`/api/trips/${item.trip_id}/destinations`, {
                          method: "POST",
                          body: { destination_id: destination.destination_id },
                        });
                        setTrip(item);
                        setScreen("trip");
                      }, "Destination added to trip.")}>
                      {item.trip_name}
                    </Button>
                  ))}
                </View>
              )}
            </>
          ) : (
            <View style={styles.emptyCard}>
              <MaterialIcons name="luggage" size={32} color="#147998" />
              <Text style={styles.cardTitle}>Sign in to see your trips</Text>
              <Button onPress={() => { setAuthMode("login"); setScreen("auth"); }}>Sign in</Button>
            </View>
          )}
        </View>
      );
    }

    if (screen === "createTrip") {
      return (
        <Card style={styles.formCard}>
          <Text style={styles.sectionTitle}>Create a trip</Text>
          <Field label="Trip name" value={form.trip_name || ""} onChangeText={(value) => change("trip_name", value)} />
          <Field label="Start date (YYYY-MM-DD)" value={form.start_date || ""} onChangeText={(value) => change("start_date", value)} />
          <Field label="End date (YYYY-MM-DD)" value={form.end_date || ""} onChangeText={(value) => change("end_date", value)} />
          <Field label="Total budget" value={form.budget || ""} onChangeText={(value) => change("budget", value)} keyboardType="decimal-pad" />
          <Field label="Budget currency (e.g. PHP)" value={form.budget_currency || "PHP"} onChangeText={(value) => change("budget_currency", value.toUpperCase())} />
          <Field label="Trip notes (optional)" value={form.description || ""} onChangeText={(value) => change("description", value)} multiline />
          <Button disabled={busy} onPress={() => act(submitTrip, "Trip created.")}>Create trip</Button>
        </Card>
      );
    }

    if (screen === "trip" && trip) {
      const plannedTotals =
        budgetSummary?.totals_by_kind_and_currency?.planned || {};
      const otherPlannedExpenses = expenses.filter(
        (item) => item.expense_kind === "planned" && !item.source_option_id
      );
      return (
        <View>
          <Text style={styles.eyebrow}>TRIP OVERVIEW</Text>
          <Text style={styles.sectionTitle}>{trip.trip_name}</Text>
          <Text style={styles.bodyText}>{trip.start_date} — {trip.end_date} · {trip.duration_days} days</Text>
          {trip.budget != null && <Text style={styles.bodyText}>Budget: {trip.budget} {trip.budget_currency}</Text>}
          <Card>
            <Text style={styles.label}>Estimated Trip Cost</Text>
            {Object.entries(plannedTotals).length ? (
              Object.entries(plannedTotals).map(([currency, amount]) => (
                <Text key={currency} style={styles.priceText}>
                  {formatHotelPrice(amount, currency)}
                </Text>
              ))
            ) : (
              <Text style={styles.muted}>No planned expenses yet.</Text>
            )}
            <Text style={styles.safetyNote}>
              Planned costs in different currencies are shown separately; no conversion is applied.
            </Text>
          </Card>
          {!!otherPlannedExpenses.length && (
            <>
              <Text style={styles.subheading}>Other planned expenses</Text>
              {otherPlannedExpenses.map((item) => (
                <Card key={item.expense_id}>
                  <Text style={styles.cardTitle}>{item.expense_name}</Text>
                  <Text style={styles.muted}>
                    {item.category} · {formatHotelPrice(item.amount, item.currency)}
                  </Text>
                </Card>
              ))}
            </>
          )}
          <View style={styles.actions}>
            <Button secondary onPress={() => setScreen("trips")}>← My trips</Button>
            {renderTripFeatures()}
          </View>
          <Text style={styles.subheading}>Destinations</Text>
          {tripDestinations.map((place) => (
            <Card key={place.trip_destination_id}>
              <Text style={styles.cardTitle}>{place.name}</Text>
              <Text style={styles.muted}>{place.city}, {place.country}</Text>
            </Card>
          ))}
          <Button secondary onPress={() => setScreen("explore")}>Explore destinations to add</Button>
          <Text style={styles.subheading}>Activities</Text>
          {activities.map((item) => <Card key={item.schedule_id}><Text style={styles.cardTitle}>{item.activity_name}</Text><Text style={styles.muted}>{item.activity_date}</Text></Card>)}
          <Field label="Activity" value={form.activity_name || ""} onChangeText={(value) => change("activity_name", value)} />
          <Field label="Activity date (YYYY-MM-DD)" value={form.activity_date || trip.start_date} onChangeText={(value) => change("activity_date", value)} />
          <Button onPress={() => act(async () => {
            await api(`/api/trips/${trip.trip_id}/schedules`, {
              method: "POST",
              body: { activity_name: form.activity_name, activity_date: form.activity_date },
            });
            resetForm();
          }, "Activity added.")}>Add activity</Button>
          <Text style={styles.subheading}>Saved transport and stay options</Text>
          {options.map((item) => {
            const details = item.details || {};
            const dates = details.dates || {};
            return (
              <Card key={item.option_id}>
                {item.option_type === "hotel" && (
                  <HotelPhoto uri={details.image_url || details.images?.[0]} style={styles.hotelImage} />
                )}
                <Text style={styles.cardTitle}>{item.title}</Text>
                {item.option_type === "hotel" && (
                  <>
                    <Text style={styles.muted}>
                      {[details.location?.city, details.location?.region, details.location?.country]
                        .filter(Boolean).join(", ") || "Location not available"}
                    </Text>
                    {!!(dates.check_in || dates.check_out) && (
                      <Text style={styles.muted}>
                        {dates.check_in || "Not available"} → {dates.check_out || "Not available"}
                        {details.nights ? ` · ${details.nights} night${details.nights === 1 ? "" : "s"}` : ""}
                      </Text>
                    )}
                    {details.search_criteria && (
                      <Text style={styles.muted}>
                        {details.search_criteria.adults ?? 0} adults
                        {details.search_criteria.children
                          ? ` · ${details.search_criteria.children} children` : ""}
                        {details.search_criteria.rooms
                          ? ` · ${details.search_criteria.rooms} room${details.search_criteria.rooms === 1 ? "" : "s"}` : ""}
                      </Text>
                    )}
                    <Field
                      label="Check-in (YYYY-MM-DD)"
                      value={hotelDateEdits[item.option_id]?.check_in ?? dates.check_in ?? ""}
                      onChangeText={(value) => setHotelDateEdits((current) => ({
                        ...current,
                        [item.option_id]: {
                          ...current[item.option_id],
                          check_in: value,
                        },
                      }))}
                    />
                    <Field
                      label="Check-out (YYYY-MM-DD)"
                      value={hotelDateEdits[item.option_id]?.check_out ?? dates.check_out ?? ""}
                      onChangeText={(value) => setHotelDateEdits((current) => ({
                        ...current,
                        [item.option_id]: {
                          ...current[item.option_id],
                          check_out: value,
                        },
                      }))}
                    />
                    <Button
                      secondary
                      disabled={busy}
                      onPress={() => updateHotelDates(item)}
                    >
                      Update stay dates
                    </Button>
                    {details.rating != null && (
                      <View style={styles.ratingRow}>
                        <MaterialIcons name="star" size={18} color="#d99624" />
                        <Text style={styles.ratingTextInline}>
                          {details.rating}{details.rating_scale == null ? "" : ` / ${details.rating_scale}`}
                        {details.review_count == null ? "" : ` · ${details.review_count} reviews`}
                        </Text>
                      </View>
                    )}
                    {details.price_per_night != null && (
                      <Text style={styles.muted}>
                        {formatHotelPrice(details.price_per_night, details.currency)} / night
                      </Text>
                    )}
                  </>
                )}
                <Text style={styles.priceText}>
                  {item.amount == null
                    ? "Planned/estimated cost: Not available"
                    : `${item.option_type === "hotel" ? "Estimated stay total" : "Planned/estimated cost"}: ${formatHotelPrice(item.amount, item.currency)}`}
                </Text>
                {item.option_type === "hotel" && details.total_price == null
                  && details.price_per_night != null && details.nights != null && (
                    <Text style={styles.muted}>
                      Estimated from the nightly rate; provider total was not returned.
                      Taxes and fees may be additional.
                    </Text>
                  )}
                <Button secondary disabled={busy} onPress={() => act(
                  () => api(`/api/saved-options/${item.option_id}`, { method: "DELETE" }),
                  "Saved option removed."
                )}>Remove option</Button>
              </Card>
            );
          })}
          <Text style={styles.safetyNote}>TravelWise does not book, buy, or process payments.</Text>
        </View>
      );
    }

    if (screen === "hotelDetails" && selectedHotel) {
      const photos = hotelImageUris(selectedHotel);
      const hotelLocation = selectedHotel.location || {};
      const displayedReviews = hotelReviews.loaded
        ? hotelReviews.items
        : Array.isArray(selectedHotel.reviews) ? selectedHotel.reviews : [];
      const reviewListingAvailable =
        Boolean(selectedHotel.provider && selectedHotel.platform_listing_id);
      const nights = hotelStayNights(selectedHotel);
      const estimatedTotal = hotelEstimate(selectedHotel);

      return (
        <View>
          <Button secondary onPress={() => setScreen("hotels")}>← Back to hotel results</Button>
          <Text style={styles.eyebrow}>HOTEL DETAILS</Text>
          <Text style={styles.sectionTitle}>{selectedHotel.name || "Hotel details"}</Text>
          <HotelPhoto
            key={photos[hotelPhotoIndex] || "no-hotel-photo"}
            uri={photos[hotelPhotoIndex]}
            style={styles.hotelDetailPhoto}
          />
          {photos.length > 1 && (
            <View style={styles.actions}>
              <Button secondary onPress={() => setHotelPhotoIndex((hotelPhotoIndex + photos.length - 1) % photos.length)}>
                Previous photo
              </Button>
              <Text style={styles.muted}>{hotelPhotoIndex + 1} of {photos.length}</Text>
              <Button secondary onPress={() => setHotelPhotoIndex((hotelPhotoIndex + 1) % photos.length)}>
                Next photo
              </Button>
            </View>
          )}
          {selectedHotel.star_rating != null && (
            <View style={styles.ratingRow}>
              <MaterialIcons name="star" size={18} color="#d99624" />
              <Text style={styles.ratingTextInline}>Hotel stars: {selectedHotel.star_rating}</Text>
            </View>
          )}
          {(selectedHotel.rating != null || selectedHotel.review_count != null) && (
            <View style={styles.ratingRow}>
              {selectedHotel.rating != null && (
                <MaterialIcons name="star" size={18} color="#d99624" />
              )}
              <Text style={styles.ratingTextInline}>
                {selectedHotel.rating == null
                  ? "Guest rating not available"
                  : `${selectedHotel.rating}${selectedHotel.rating_scale == null ? "" : ` / ${selectedHotel.rating_scale}`}`}
                {selectedHotel.review_count == null
                  ? ""
                  : ` · ${selectedHotel.review_count} review${selectedHotel.review_count === 1 ? "" : "s"}`}
              </Text>
            </View>
          )}
          {(selectedHotel.price_per_night != null || selectedHotel.total_price != null) && (
            <Card>
              {selectedHotel.price_per_night != null && (
                <Text style={styles.priceText}>
                  {formatHotelPrice(selectedHotel.price_per_night, selectedHotel.currency)} / night
                </Text>
              )}
              {selectedHotel.total_price != null && (
                <Text style={styles.priceText}>
                  Total stay: {formatHotelPrice(selectedHotel.total_price, selectedHotel.currency)}
                </Text>
              )}
              {selectedHotel.total_price == null && estimatedTotal != null && (
                <Text style={styles.muted}>
                  Estimated stay total: {formatHotelPrice(estimatedTotal, selectedHotel.currency)}
                  {nights == null ? "" : ` · ${nights} night${nights === 1 ? "" : "s"}`}
                  {" · Taxes and fees may be additional."}
                </Text>
              )}
              {selectedHotel.taxes != null && (
                <Text style={styles.muted}>Taxes: {JSON.stringify(selectedHotel.taxes)}</Text>
              )}
              {selectedHotel.fees != null && (
                <Text style={styles.muted}>Fees: {JSON.stringify(selectedHotel.fees)}</Text>
              )}
            </Card>
          )}
          <Text style={styles.subheading}>Location</Text>
          <Text style={styles.bodyText}>
            {[hotelLocation.address, hotelLocation.city, hotelLocation.region, hotelLocation.country]
              .filter(Boolean).join(", ") || "Location not available"}
          </Text>
          {!!selectedHotel.description && (
            <Text style={styles.bodyText}>{displayHotelValue(selectedHotel.description)}</Text>
          )}
          {!!selectedHotel.review_summary && (
            <Text style={styles.bodyText}>
              Review summary: {displayHotelValue(selectedHotel.review_summary)}
            </Text>
          )}
          <Text style={styles.subheading}>Stay information</Text>
          {selectedHotel.room_type != null && <Text style={styles.bodyText}>Room: {displayHotelValue(selectedHotel.room_type)}</Text>}
          {selectedHotel.bed_type != null && <Text style={styles.bodyText}>Bed: {displayHotelValue(selectedHotel.bed_type)}</Text>}
          {selectedHotel.rooms != null && <Text style={styles.bodyText}>Rooms: {selectedHotel.rooms}</Text>}
          {selectedHotel.search_criteria && (
            <Text style={styles.bodyText}>
              Guests searched: {selectedHotel.search_criteria.adults ?? "Not available"} adults
              {selectedHotel.search_criteria.children
                ? `, ${selectedHotel.search_criteria.children} children` : ""}
            </Text>
          )}
          {selectedHotel.max_occupancy != null && <Text style={styles.bodyText}>Maximum occupancy: {selectedHotel.max_occupancy}</Text>}
          {selectedHotel.bedrooms != null && <Text style={styles.bodyText}>Bedrooms: {selectedHotel.bedrooms}</Text>}
          {selectedHotel.bathrooms != null && <Text style={styles.bodyText}>Bathrooms: {selectedHotel.bathrooms}</Text>}
          {selectedHotel.host != null && <Text style={styles.bodyText}>Host: {String(selectedHotel.host)}</Text>}
          {selectedHotel.property_type != null && <Text style={styles.bodyText}>Property type: {displayHotelValue(selectedHotel.property_type)}</Text>}
          {selectedHotel.availability != null && (
            <Text style={styles.bodyText}>Availability: {typeof selectedHotel.availability === "string"
              ? selectedHotel.availability : JSON.stringify(selectedHotel.availability)}</Text>
          )}
          {selectedHotel.cancellation_policy != null && (
            <Text style={styles.bodyText}>Cancellation: {displayHotelValue(selectedHotel.cancellation_policy)}</Text>
          )}
          {Array.isArray(selectedHotel.amenities) && selectedHotel.amenities.length > 0 && (
            <>
              <Text style={styles.subheading}>Amenities</Text>
              <Text style={styles.bodyText}>
                {selectedHotel.amenities.map(displayHotelValue).join(" · ")}
              </Text>
            </>
          )}
          {!!selectedHotel.dates && (
            <Text style={styles.muted}>
              Stay: {selectedHotel.dates.check_in || "Not available"} → {selectedHotel.dates.check_out || "Not available"}
              {nights == null ? "" : ` · ${nights} night${nights === 1 ? "" : "s"}`}
            </Text>
          )}
          {!!selectedHotel.provider && <Text style={styles.muted}>Provider: {selectedHotel.provider}</Text>}
          {!!selectedHotel.price_source && <Text style={styles.muted}>Price source: {selectedHotel.price_source}</Text>}
          {selectedHotel.booking_url?.startsWith("https://") && (
            <Text
              accessibilityRole="link"
              onPress={() => Linking.openURL(selectedHotel.booking_url)}
              style={styles.attribution}
            >
              View provider information
            </Text>
          )}
          <Text style={styles.subheading}>Guest reviews</Text>
          {reviewListingAvailable && (
            <Button
              secondary
              disabled={hotelReviews.loading}
              onPress={() => loadHotelReviews(selectedHotel)}
            >
              {hotelReviews.loading ? "Loading reviews…" : hotelReviews.loaded ? "Refresh reviews" : "Load provider reviews"}
            </Button>
          )}
          {!!hotelReviews.error && <Text accessibilityRole="alert" style={styles.error}>{hotelReviews.error}</Text>}
          {displayedReviews.map((review, index) => {
            if (!review || typeof review !== "object") return null;
            const reviewBody = review.text || review.content || review.comment;
            return (
              <Card key={`${review.id || review.title || "review"}-${index}`}>
                {review.title != null && <Text style={styles.cardTitle}>{String(review.title)}</Text>}
                {review.rating != null && (
                  <View style={styles.ratingRow}>
                    <MaterialIcons name="star" size={18} color="#d99624" />
                    <Text style={styles.ratingTextInline}>
                      {String(review.rating)}{review.ratingScale == null ? "" : ` / ${review.ratingScale}`}
                    </Text>
                  </View>
                )}
                {(review.author || review.date || review.createdAt) && (
                  <Text style={styles.muted}>
                    {[review.author, review.date || review.createdAt].filter(Boolean).map(String).join(" · ")}
                  </Text>
                )}
                {reviewBody != null && <Text style={styles.bodyText}>{String(reviewBody)}</Text>}
                {review.ownerResponse != null && (
                  <Text style={styles.muted}>Owner response: {String(review.ownerResponse)}</Text>
                )}
              </Card>
            );
          })}
          {!displayedReviews.length && !hotelReviews.loading && !hotelReviews.error && (
            <Text style={styles.muted}>
              {hotelReviews.loaded ? "No detailed reviews were returned by the provider." : "No review details were included with this result."}
            </Text>
          )}
          <Button disabled={busy} onPress={() => saveOption("hotel", selectedHotel)}>＋ Add to Trip</Button>
          <Text style={styles.safetyNote}>
            Planning only. Saving this hotel updates planned trip costs; it does not book or purchase.
          </Text>
        </View>
      );
    }

    if (screen === "hotels") {
      const isFlight = screen === "flights";
      return (
        <View>
          <Text style={styles.eyebrow}>PLANNING SEARCH</Text>
          <Text style={styles.sectionTitle}>Find hotels</Text>
          <Text style={styles.safetyNote}>Each search checks live StayingAPI results for Asia. Offers are for planning only—TravelWise does not purchase or book.</Text>
          {isFlight ? (
            <>
              <Field label="Origin airport code (e.g. MNL)" value={form.origin || ""} onChangeText={(value) => change("origin", value.toUpperCase())} />
              <Field label="Destination airport code (e.g. NRT)" value={form.destination_code || ""} onChangeText={(value) => change("destination_code", value.toUpperCase())} />
              <Field label="Departure date (YYYY-MM-DD)" value={form.departure_date || trip.start_date || ""} onChangeText={(value) => change("departure_date", value)} />
            </>
          ) : (
            <>
              <Field label="City name (e.g. Tokyo)" value={form.city || ""} onChangeText={(value) => change("city", value)} />
              <Field label="Asian country code (e.g. JP, TH, PH)" value={form.hotel_country || "JP"} onChangeText={(value) => change("hotel_country", value.toUpperCase())} />
              <Field label="Check-in date (YYYY-MM-DD)" value={form.check_in || trip.start_date || ""} onChangeText={(value) => change("check_in", value)} />
              <Field label="Check-out date (YYYY-MM-DD)" value={form.check_out || trip.end_date || ""} onChangeText={(value) => change("check_out", value)} />
              <Field label="Adults" value={form.hotel_adults || "2"} onChangeText={(value) => change("hotel_adults", value)} keyboardType="number-pad" />
              <Field label="Rooms" value={form.hotel_rooms || "1"} onChangeText={(value) => change("hotel_rooms", value)} keyboardType="number-pad" />
              <Field label="Children" value={form.hotel_children || "0"} onChangeText={(value) => change("hotel_children", value)} keyboardType="number-pad" />
              <Field label="Child ages (comma-separated)" value={form.hotel_child_ages || ""} onChangeText={(value) => change("hotel_child_ages", value)} placeholder="e.g. 4, 8" />
              <Field
                label="Currency preference"
                value={form.hotel_currency || trip.budget_currency || ""}
                onChangeText={(value) => change("hotel_currency", value.toUpperCase())}
                placeholder="Trip currency or server default"
              />
              <Text style={styles.safetyNote}>Hotel searches are limited to Asia. Provider prices remain in their reported currency; no exchange conversion is applied.</Text>
            </>
          )}
          <Button disabled={busy} onPress={() => act(searchHotels)}>Search hotels</Button>
          {searchResults.map((result, index) => (
            <Card key={`${searchKind}-${result.hotel_id || result.flight_number || index}`}>
              {isFlight ? (
                <>
                  <View style={styles.flightCarrier}>
                    {result.airline_logo_url && !unavailableImages[`flight-${index}`] ? (
                      <Image
                        source={{ uri: result.airline_logo_url }}
                        style={styles.airlineLogo}
                        onError={() => setUnavailableImages((old) => ({ ...old, [`flight-${index}`]: true }))}
                      />
                    ) : (
                      <View style={[styles.airlineLogo, styles.imageFallback]}>
                        <Text style={styles.logoUnavailable}>Image unavailable</Text>
                      </View>
                    )}
                    <View style={styles.flightCarrierInfo}>
                      <Text style={styles.cardTitle}>
                        {result.airline || `Airline name not available${result.airline_code ? ` · ${result.airline_code}` : ""}`}
                      </Text>
                      <Text style={styles.muted}>
                        {result.flight_number || "Not available"}
                        {result.airline_code ? ` · ${result.airline_code}` : ""}
                      </Text>
                    </View>
                  </View>
                  {result.airline_logo_attribution && result.airline_logo_source_url && (
                    <Text
                      accessibilityRole="link"
                      onPress={() => Linking.openURL(result.airline_logo_source_url)}
                      style={styles.attribution}
                    >
                      Airline logo: {result.airline_logo_attribution}
                    </Text>
                  )}
                  <Text style={styles.routeTitle}>
                    {result.origin || "Not available"} → {result.destination || "Not available"}
                  </Text>
                  {(result.segments || []).map((segment, segmentIndex) => (
                    <View key={`${segment.flight_number || "segment"}-${segmentIndex}`} style={styles.segmentRow}>
                      <Text style={styles.muted}>
                        {segment.airline || "Not available"} · {segment.flight_number || "Not available"}
                      </Text>
                      <Text style={styles.bodyText}>
                        {segment.origin || "Not available"} {formatTravelDateTime(segment.departure_at)}
                        {" → "}
                        {segment.destination || "Not available"} {formatTravelDateTime(segment.arrival_at)}
                      </Text>
                    </View>
                  ))}
                  {!result.segments?.length && (
                    <>
                      <Text style={styles.bodyText}>Departure: {formatTravelDateTime(result.departure_at)}</Text>
                      <Text style={styles.bodyText}>Arrival: {formatTravelDateTime(result.arrival_at)}</Text>
                    </>
                  )}
                  <Text style={styles.muted}>Duration: {formatTravelDuration(result.duration)}</Text>
                  <Text style={styles.muted}>
                    {result.stops == null ? "Stops: Not available" : result.stops === 0 ? "Non-stop" : `${result.stops} stop${result.stops === 1 ? "" : "s"}`}
                  </Text>
                  <Text style={styles.priceText}>
                    {formatPrice(result.price, result.currency)}
                  </Text>
                  <Text style={styles.muted}>Listed/estimated planned flight cost</Text>
                </>
              ) : (
                <>
                  <HotelPhoto uri={hotelImageUris(result)[0]} style={styles.hotelImage} />
                  <Text style={styles.cardTitle}>{result.name || "Not available"}</Text>
                  {!!result.searched_at && (
                    <Text style={styles.liveAvailability}>
                      ● Live provider result · checked {result.searched_at}
                    </Text>
                  )}
                  <Text style={styles.muted}>
                    Location: {[result.location?.city, result.location?.country].filter(Boolean).join(", ")
                      || result.location?.city_code
                      || "Not available"}
                  </Text>
                  {result.rating != null ? (
                    <View style={styles.ratingRow}>
                      <MaterialIcons name="star" size={18} color="#d99624" />
                      <Text style={styles.ratingTextInline}>
                        {result.rating}{result.rating_scale == null ? "" : ` / ${result.rating_scale}`}
                      {result.review_count == null ? "" : ` · ${result.review_count} review${result.review_count === 1 ? "" : "s"}`}
                      </Text>
                    </View>
                  ) : result.review_count != null ? (
                    <Text style={styles.ratingText}>
                      {result.review_count} review{result.review_count === 1 ? "" : "s"}
                    </Text>
                  ) : null}
                  {result.star_rating != null && (
                    <Text style={styles.muted}>Hotel stars: {displayHotelValue(result.star_rating)}</Text>
                  )}
                  {result.availability != null && (
                    <Text style={styles.bodyText}>
                      Provider availability: {displayHotelValue(result.availability)}
                    </Text>
                  )}
                  {result.price_per_night != null && (
                    <Text style={styles.priceText}>
                      {formatHotelPrice(result.price_per_night, result.currency)} / night
                    </Text>
                  )}
                  {result.total_price != null && (
                    <Text style={styles.muted}>
                      Total stay: {formatHotelPrice(result.total_price, result.currency)}
                    </Text>
                  )}
                  {result.total_price == null && hotelEstimate(result) != null && (
                    <Text style={styles.muted}>
                      Estimated total for {hotelStayNights(result)} night{hotelStayNights(result) === 1 ? "" : "s"}:{" "}
                      {formatHotelPrice(hotelEstimate(result), result.currency)}
                      {" · Taxes and fees may be additional."}
                    </Text>
                  )}
                  {result.price_per_night == null && result.total_price == null && (
                    <Text style={styles.muted}>Price not available</Text>
                  )}
                  {!!result.description && (
                    <Text numberOfLines={2} style={styles.cardDescription}>{result.description}</Text>
                  )}
                  {result.booking_url?.startsWith("https://") && (
                    <Text
                      accessibilityRole="link"
                      onPress={() => Linking.openURL(result.booking_url)}
                      style={styles.attribution}
                    >
                      Provider link
                    </Text>
                  )}
                  {result.image_attribution && result.image_source_url && (
                    <Text
                      accessibilityRole="link"
                      onPress={() => Linking.openURL(result.image_source_url)}
                      style={styles.attribution}
                    >
                      Photo: {result.image_attribution} · {result.image_license || "license details"}
                    </Text>
                  )}
                </>
              )}
              <Text style={styles.safetyNote}>Planning only. Adding this offer records a planned estimate; it does not purchase or book.</Text>
              {isFlight ? (
                <Button disabled={busy} onPress={() => saveOption("flight", result)}>Add to Trip</Button>
              ) : (
                <View style={styles.actions}>
                  <Button secondary onPress={() => {
                    setSelectedHotel(result);
                    setHotelPhotoIndex(0);
                    setHotelReviews({
                      items: Array.isArray(result.reviews) ? result.reviews : [],
                      loading: false,
                      loaded: false,
                      error: "",
                    });
                    setError("");
                    setScreen("hotelDetails");
                  }}>View Details</Button>
                  <Button disabled={busy} onPress={() => saveOption("hotel", result)}>＋ Add to Trip</Button>
                </View>
              )}
            </Card>
          ))}
          {searchKind === (isFlight ? "flight" : "hotel") && !searchResults.length && (
            <Text style={styles.muted}>No hotels were found for those dates. Try another city or travel dates.</Text>
          )}
          {trip && (
            <View style={styles.tripSearchPicker}>
              <Text style={styles.label}>Save search results to: {trip.trip_name}</Text>
              <View style={styles.actions}>
                {trips.map((item) => (
                  <Button
                    key={item.trip_id}
                    secondary
                    onPress={() => {
                      setTrip(item);
                      setSearchResults([]);
                      setSearchKind("");
                      resetForm();
                    }}
                  >
                    {item.trip_name}
                  </Button>
                ))}
              </View>
            </View>
          )}
        </View>
      );
    }

    if (screen === "budget" || screen === "expenses") {
      const totals = budgetSummary?.totals_by_kind_and_currency || { planned: {}, actual: {} };
      return (
        <View>
          <Text style={styles.eyebrow}>TRIP COSTS</Text>
          <Text style={styles.sectionTitle}>{screen === "expenses" ? "Expenses" : "Budget"}</Text>
          <View style={styles.detailGrid}>
            <Card><Text style={styles.label}>Total budget</Text><Text style={styles.cardTitle}>{trip.budget == null ? "Not set" : `${trip.budget} ${trip.budget_currency}`}</Text></Card>
            <Card><Text style={styles.label}>Total planned cost</Text><Text style={styles.cardTitle}>{Object.entries(totals.planned || {}).map(([currency, amount]) => `${amount} ${currency}`).join(" · ") || "None yet"}</Text></Card>
            <Card><Text style={styles.label}>Actual expenses</Text><Text style={styles.cardTitle}>{Object.entries(totals.actual || {}).map(([currency, amount]) => `${amount} ${currency}`).join(" · ") || "None yet"}</Text></Card>
            <Card><Text style={styles.label}>Remaining budget</Text><Text style={styles.cardTitle}>{budgetSummary?.budget?.remaining == null ? "Not available" : `${budgetSummary.budget.remaining} ${budgetSummary.budget.budget_currency}`}</Text></Card>
            <Card><Text style={styles.label}>Actual minus planned</Text><Text style={styles.cardTitle}>{Object.entries(budgetSummary?.variance_by_currency || {}).map(([currency, amount]) => `${amount > 0 ? "+" : ""}${amount} ${currency}`).join(" · ") || "No comparison yet"}</Text></Card>
          </View>
          <Text style={styles.subheading}>Record an expense</Text>
          <Field label="Expense name" value={form.expense_name || ""} onChangeText={(value) => change("expense_name", value)} />
          <Field label="Category (flights, hotels, activities, transportation, food, other)" value={form.category || "other"} onChangeText={(value) => change("category", value)} />
          <Field label="Amount" value={form.amount || ""} onChangeText={(value) => change("amount", value)} keyboardType="decimal-pad" />
          <Field label="Currency" value={form.currency || trip.budget_currency || "PHP"} onChangeText={(value) => change("currency", value.toUpperCase())} />
          <Field label="Expense date (YYYY-MM-DD)" value={form.expense_date || new Date().toISOString().slice(0, 10)} onChangeText={(value) => change("expense_date", value)} />
          <Field label="Type (planned or actual)" value={form.expense_kind || "planned"} onChangeText={(value) => change("expense_kind", value.toLowerCase())} />
          <Button disabled={busy} onPress={() => act(async () => {
            await api(`/api/trips/${trip.trip_id}/expenses`, {
              method: "POST",
              body: {
                ...form,
                amount: Number(form.amount),
                currency: form.currency || trip.budget_currency || "PHP",
                expense_date: form.expense_date || new Date().toISOString().slice(0, 10),
                expense_kind: form.expense_kind || "planned",
              },
            });
            resetForm();
          }, "Expense recorded.")}>Save expense</Button>
          {expenses.map((item) => (
            <Card key={item.expense_id}>
              <Text style={styles.cardTitle}>{item.expense_name} · {item.expense_kind}</Text>
              <Text style={styles.muted}>{item.amount} {item.currency} · {item.category} · {item.expense_date}</Text>
              <Button secondary onPress={() => act(() => api(`/api/expenses/${item.expense_id}`, { method: "DELETE" }), "Expense deleted.")}>Delete expense</Button>
            </Card>
          ))}
          <Text style={styles.safetyNote}>Flight and hotel prices are listed estimates recorded as planned costs. Planned and actual amounts are separate; different currencies are not combined. No purchase or booking is made.</Text>
        </View>
      );
    }

    if (screen === "checklist") {
      return (
        <View>
          <Text style={styles.eyebrow}>GET READY</Text>
          <Text style={styles.sectionTitle}>Trip checklist</Text>
          <Button onPress={() => act(async () => {
            await api(`/api/trips/${trip.trip_id}/checklists`, { method: "POST", body: { checklist_name: form.checklist_name || "Packing list" } });
            resetForm();
          }, "Checklist created.")}>＋ Create a checklist</Button>
          <Field label="New checklist item" value={form.item_name || ""} onChangeText={(value) => change("item_name", value)} />
          {checklists.map((list) => (
            <Card key={list.checklist_id}>
              <Text style={styles.cardTitle}>{list.checklist_name}</Text>
              {list.items?.map((item) => (
                  <View key={item.item_id} style={styles.checklistRow}>
                    <TouchableOpacity style={styles.checklistLabel} onPress={() => act(() => api(`/api/checklist-items/${item.item_id}/toggle`, { method: "POST" }), "Checklist updated.")}>
                      <MaterialIcons
                        name={item.is_completed ? "check-box" : "check-box-outline-blank"}
                        size={21}
                        color={item.is_completed ? "#147998" : "#8196a8"}
                      />
                      <Text style={item.is_completed ? styles.completedItem : styles.bodyText}>{item.item_name}</Text>
                    </TouchableOpacity>
                    <Button secondary onPress={() => {
                      setEditingChecklistItem(item);
                      change("item_name", item.item_name);
                    }}>Edit</Button>
                    <Button secondary onPress={() => act(() => api(`/api/checklist-items/${item.item_id}`, { method: "DELETE" }), "Checklist item deleted.")}>Delete</Button>
                  </View>
                ))}
                <Button secondary onPress={() => act(async () => {
                  if (editingChecklistItem) {
                    await api(`/api/checklist-items/${editingChecklistItem.item_id}`, {
                      method: "PATCH",
                      body: { item_name: form.item_name },
                    });
                    setEditingChecklistItem(null);
                  } else {
                    await api(`/api/checklists/${list.checklist_id}/items`, {
                      method: "POST",
                      body: { item_name: form.item_name },
                    });
                  }
                  resetForm();
                }, editingChecklistItem ? "Checklist item updated." : "Item added.")}>
                  {editingChecklistItem ? "Save item" : "Add item"}
                </Button>
            </Card>
          ))}
          {!checklists.length && <Text style={styles.muted}>Create a checklist to add passport, clothes, adapter, and other reminders.</Text>}
        </View>
      );
    }

    if (screen === "notes") {
      return (
        <View>
          <Text style={styles.eyebrow}>TRIP MEMOS</Text>
          <Text style={styles.sectionTitle}>Notes</Text>
          <Field label="Note title" value={form.title || ""} onChangeText={(value) => change("title", value)} />
          <Field label="Write a note" value={form.content || ""} onChangeText={(value) => change("content", value)} multiline />
          <Button disabled={busy} onPress={() => act(async () => {
            if (editingNote) {
              await api(`/api/notes/${editingNote.note_id}`, { method: "PATCH", body: form });
              setEditingNote(null);
            } else {
              await api(`/api/trips/${trip.trip_id}/notes`, { method: "POST", body: form });
            }
            resetForm();
          }, editingNote ? "Note updated." : "Note saved.")}>{editingNote ? "Update note" : "Save note"}</Button>
          {notes.map((item) => (
            <Card key={item.note_id}>
              <Text style={styles.cardTitle}>{item.title}</Text>
              <Text style={styles.bodyText}>{item.content}</Text>
              <Button secondary onPress={() => {
                setEditingNote(item);
                change("title", item.title);
                change("content", item.content);
              }}>Edit note</Button>
              <Button secondary onPress={() => act(() => api(`/api/notes/${item.note_id}`, { method: "DELETE" }), "Note deleted.")}>Delete note</Button>
            </Card>
          ))}
        </View>
      );
    }

    if (screen === "profile") {
      return (
        <View style={styles.screenSection}>
          <Text style={styles.eyebrow}>ACCOUNT</Text>
          <Text style={styles.screenTitle}>Your profile</Text>
          {user ? (
            <>
              <View style={styles.profileCard}>
                <View style={styles.profileAvatarWrap}>
                  {profilePhoto ? (
                    <Image
                      source={{ uri: profilePhoto }}
                      style={styles.profileAvatar}
                      onError={() => setProfilePhoto(null)}
                    />
                  ) : (
                    <MaterialIcons name="person" size={48} color="#147998" />
                  )}
                  <TouchableOpacity
                    accessibilityRole="button"
                    accessibilityLabel="Change profile picture"
                    disabled={profilePhotoBusy}
                    onPress={chooseProfilePhoto}
                    style={styles.profileCamera}
                  >
                    {profilePhotoBusy
                      ? <ActivityIndicator color="#ffffff" size="small" />
                      : <MaterialIcons name="camera-alt" size={17} color="#ffffff" />}
                  </TouchableOpacity>
                </View>
                <Text style={styles.profileName}>{user.full_name}</Text>
                <Text style={styles.profileEmail}>{user.email}</Text>
                <TouchableOpacity
                  accessibilityRole="button"
                  disabled={profilePhotoBusy}
                  onPress={chooseProfilePhoto}
                  style={styles.profilePhotoAction}
                >
                  <MaterialIcons name="photo" size={18} color="#147998" />
                  <Text style={styles.profilePhotoActionText}>
                    {profilePhoto ? "Change photo" : "Add a profile photo"}
                  </Text>
                </TouchableOpacity>
                {profilePhoto ? (
                  <TouchableOpacity
                    accessibilityRole="button"
                    disabled={profilePhotoBusy}
                    onPress={removeProfilePhoto}
                    style={styles.removePhotoAction}
                  >
                    <MaterialIcons name="delete-outline" size={17} color="#8a5260" />
                    <Text style={styles.removePhotoText}>Remove photo</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
              <View style={styles.profileSettings}>
                <View style={styles.profileSettingRow}>
                  <View style={styles.profileSettingIcon}>
                    <MaterialIcons name="verified-user" size={20} color="#147998" />
                  </View>
                  <View style={styles.profileSettingCopy}>
                    <Text style={styles.cardTitle}>Account security</Text>
                    <Text style={styles.muted}>Your password is securely hashed.</Text>
                  </View>
                </View>
                <View style={styles.profileSettingRow}>
                  <View style={styles.profileSettingIcon}>
                    <MaterialIcons name="notifications-none" size={20} color="#147998" />
                  </View>
                  <View style={styles.profileSettingCopy}>
                    <Text style={styles.cardTitle}>Login alerts</Text>
                    <Text style={styles.muted}>Security alerts are sent to your verified email.</Text>
                  </View>
                </View>
              </View>
              <Button secondary icon="logout" onPress={() => act(async () => {
                await api("/api/auth/logout", { method: "POST", body: {} });
                setUser(null);
                setTrip(null);
                await refreshCsrf();
                setScreen("welcome");
              }, "Signed out.")}>Sign out</Button>
            </>
          ) : (
            <View style={styles.emptyCard}>
              <MaterialIcons name="person-outline" size={32} color="#147998" />
              <Text style={styles.cardTitle}>You are signed out</Text>
              <Button onPress={() => { setAuthMode("login"); setScreen("auth"); }}>Sign in</Button>
            </View>
          )}
        </View>
      );
    }

    return <Text style={styles.muted}>Choose a section to get started.</Text>;
  }

  const showBottomTabs = Boolean(
    user && TAB_ITEMS.some(([, tabScreen]) => tabScreen === screen)
  );
  const showBackHeader = !showBottomTabs && screen !== "welcome";
  const navigateBack = () => {
    if (screen === "destination") setScreen("explore");
    else if (screen === "hotelDetails") setScreen("hotels");
    else if (["trip", "createTrip"].includes(screen)) setScreen("trips");
    else setScreen(user ? "home" : "welcome");
  };

  if (!iconFontLoaded) {
    return (
      <SafeAreaProvider>
        <SafeAreaView style={styles.safeArea} edges={["top", "right", "bottom", "left"]}>
          <ActivityIndicator color="#147998" style={styles.sectionLoader} />
        </SafeAreaView>
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safeArea} edges={["top", "right", "bottom", "left"]}>
        <StatusBar barStyle="dark-content" backgroundColor="#f8fbfc" />
        <KeyboardAvoidingView
          style={styles.app}
          behavior={Platform.OS === "ios" ? "padding" : "height"}
        >
        {!showBottomTabs && screen !== "welcome" && (
          <View style={styles.header}>
            {showBackHeader ? (
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="Go back"
                onPress={navigateBack}
                style={styles.headerBack}
              >
                <MaterialIcons name="arrow-back" size={22} color="#21445a" />
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel="Wize home"
              onPress={() => setScreen(user ? "home" : "welcome")}
              style={styles.brandLink}
            >
              <Image source={require("./static/logo-160.png")} style={styles.brandLogo} resizeMode="contain" />
              <Text style={styles.brand}>Wize</Text>
            </TouchableOpacity>
            <View style={styles.headerActions}>
              {user ? (
                <TouchableOpacity
                  accessibilityRole="button"
                  accessibilityLabel="Open profile"
                  onPress={() => setScreen("profile")}
                  style={styles.headerProfileButton}
                >
                  <MaterialIcons name="person" size={21} color="#147998" />
                </TouchableOpacity>
              ) : screen === "welcome" ? (
                <TouchableOpacity
                  accessibilityRole="button"
                  onPress={() => { setAuthMode("login"); setScreen("auth"); }}
                  style={styles.headerSignIn}
                >
                  <Text style={styles.headerSignInText}>Sign in</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        )}
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          {notice ? <Text style={styles.notice}>{notice}</Text> : null}
          {busy && <ActivityIndicator color="#147998" style={styles.busyIndicator} />}
          {renderScreen()}
        </ScrollView>
        {showBottomTabs ? (
          <View style={styles.bottomTabs}>
            {TAB_ITEMS.map(([label, tabScreen, icon]) => {
              const active = screen === tabScreen;
              return (
                <TouchableOpacity
                  key={tabScreen}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={label}
                  onPress={() => {
                    setError("");
                    setNotice("");
                    setScreen(tabScreen);
                  }}
                  style={styles.tabButton}
                >
                  <View style={[styles.tabIconWrap, active && styles.tabIconWrapActive]}>
                    <MaterialIcons
                      name={icon}
                      size={22}
                      color={active ? "#116f8e" : "#708792"}
                    />
                  </View>
                  <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        ) : null}
        </KeyboardAvoidingView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f8fbfc" },
  app: { flex: 1, backgroundColor: "#f8fbfc" },
  header: { minHeight: 58, paddingHorizontal: 20, paddingVertical: 8, backgroundColor: "#f8fbfc", flexDirection: "row", alignItems: "center", gap: 12 },
  headerBack: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  brandLink: { flexDirection: "row", alignItems: "center", gap: 8 },
  brandLogo: { width: 34, height: 34 },
  brand: { color: "#0756ad", fontWeight: "900", fontSize: 21, letterSpacing: -0.7 },
  brandDot: { color: "#13c4e8" },
  headerActions: { marginLeft: "auto", flexDirection: "row", alignItems: "center" },
  navText: { color: "#45627a", fontSize: 14, fontWeight: "600", paddingVertical: 8 },
  headerProfileButton: { width: 40, height: 40, borderRadius: 20, backgroundColor: "#e8f4f5", alignItems: "center", justifyContent: "center" },
  headerSignIn: { minHeight: 40, justifyContent: "center", paddingHorizontal: 12 },
  headerSignInText: { color: "#147998", fontSize: 14, fontWeight: "700" },
  content: { width: "100%", alignSelf: "center", paddingHorizontal: 20, paddingTop: 16, paddingBottom: 30 },
  hero: { minHeight: 550, maxWidth: 820, justifyContent: "center", paddingVertical: 50 },
  eyebrow: { color: "#398297", fontSize: 10, fontWeight: "800", letterSpacing: 1.15, marginBottom: 8 },
  heroTitle: { color: "#123354", fontSize: 58, fontWeight: "800", letterSpacing: -2.2, lineHeight: 65 },
  heroSubtitle: { maxWidth: 620, color: "#536f86", fontSize: 18, lineHeight: 28, marginTop: 18 },
  heroActions: { marginTop: 30 },
  sectionTitle: { color: "#183b4e", fontSize: 27, fontWeight: "800", letterSpacing: -0.5, marginBottom: 14 },
  subheading: { color: "#183b4e", fontSize: 19, fontWeight: "750", marginTop: 22, marginBottom: 8 },
  bodyText: { color: "#405e77", fontSize: 15, lineHeight: 23, marginTop: 8 },
  muted: { color: "#617b92", fontSize: 14, lineHeight: 21, marginTop: 5 },
  safetyNote: { color: "#536f86", fontSize: 13, lineHeight: 20, marginTop: 14 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 18, marginBottom: 18, alignItems: "center" },
  button: { minHeight: 46, flexDirection: "row", alignItems: "center", justifyContent: "center", alignSelf: "flex-start", backgroundColor: "#147998", paddingVertical: 12, paddingHorizontal: 17, borderRadius: 13, marginTop: 8, marginRight: 8 },
  buttonIcon: { marginRight: 7 },
  buttonText: { color: "#ffffff", fontSize: 14, fontWeight: "700" },
  buttonSecondary: { backgroundColor: "#e8f4f5" },
  buttonSecondaryText: { color: "#126c91" },
  disabled: { opacity: 0.55 },
  card: { backgroundColor: "#ffffff", borderColor: "#e6eef0", borderWidth: 1, borderRadius: 18, padding: 16, marginVertical: 7, shadowColor: "#173c4c", shadowOpacity: 0.045, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 1 },
  cardTitle: { color: "#183b4e", fontSize: 16, fontWeight: "700" },
  field: { width: "100%", marginBottom: 8 },
  label: { color: "#365873", fontSize: 13, fontWeight: "700", marginTop: 7, marginBottom: 6 },
  input: { width: "100%", minHeight: 48, borderColor: "#d6e4e7", borderWidth: 1, backgroundColor: "#ffffff", color: "#183b4e", borderRadius: 13, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15 },
  multiline: { minHeight: 100, textAlignVertical: "top" },
  formCard: { width: "100%", alignSelf: "center", padding: 20 },
  destinationGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: 14, marginTop: 12 },
  destinationCard: { width: "100%", backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e6eef0", borderRadius: 18, overflow: "hidden" },
  destinationImage: { width: "100%", aspectRatio: 16 / 9, backgroundColor: "#e5f0f2" },
  hotelImage: { width: "100%", height: 190, borderRadius: 10, marginBottom: 10 },
  hotelDetailPhoto: { width: "100%", height: 320, borderRadius: 18, marginTop: 12 },
  hotelPhotoFrame: { position: "relative", overflow: "hidden", backgroundColor: "#e5f8fd" },
  hotelPhotoImage: { width: "100%", height: "100%", position: "absolute", left: 0, top: 0 },
  imageLoading: { position: "absolute", alignSelf: "center", top: "45%" },
  airlineLogo: { width: 64, height: 54, borderRadius: 8, backgroundColor: "#f2f8fc" },
  imageFallback: { alignItems: "center", justifyContent: "center", backgroundColor: "#e7f0f2" },
  fallbackEmoji: { color: "#0877d8", fontSize: 44 },
  logoUnavailable: { color: "#617b92", fontSize: 12, textAlign: "center", paddingHorizontal: 8 },
  flightCarrier: { flexDirection: "row", alignItems: "center", gap: 13, marginBottom: 10 },
  flightCarrierInfo: { flex: 1 },
  routeTitle: { color: "#123354", fontSize: 21, fontWeight: "800", marginTop: 12 },
  segmentRow: { borderLeftWidth: 2, borderLeftColor: "#13c4e8", paddingLeft: 10, marginTop: 8 },
  priceText: { color: "#0756ad", fontSize: 20, fontWeight: "800", marginTop: 12 },
  ratingText: { color: "#0877a7", fontSize: 16, fontWeight: "700", marginTop: 8 },
  liveAvailability: { color: "#16734b", fontSize: 12, fontWeight: "700", marginTop: 5 },
  destinationInfo: { padding: 14 },
  cardDescription: { color: "#536f86", lineHeight: 20, marginTop: 9, minHeight: 40 },
  detailImage: { width: "100%", aspectRatio: 16 / 9, borderRadius: 18, marginTop: 16, marginBottom: 20 },
  detailGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginVertical: 12 },
  attribution: { color: "#617b92", fontSize: 12, lineHeight: 18, marginTop: 8, textDecorationLine: "underline" },
  tripGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 12 },
  featureGrid: { flexDirection: "row", flexWrap: "wrap", gap: 4 },
  tripSearchPicker: { marginTop: 24 },
  checklistRow: { flexDirection: "row", alignItems: "center", paddingVertical: 7, gap: 10 },
  checklistLabel: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  checkMark: { fontSize: 20, color: "#0877d8" },
  completedItem: { color: "#8196a8", textDecorationLine: "line-through" },
  homeGrid: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 28, paddingVertical: 70 },
  homeIntro: { flex: 2, minWidth: 280, maxWidth: 670 },
  homeSide: { flex: 1, minWidth: 250, maxWidth: 360, padding: 24 },
  error: { color: "#a12c25", backgroundColor: "#fff0ed", borderColor: "#f2c8c0", borderWidth: 1, borderRadius: 9, padding: 12, marginBottom: 14 },
  notice: { color: "#165d46", backgroundColor: "#e7f5ec", borderColor: "#cce8d5", borderWidth: 1, borderRadius: 9, padding: 12, marginBottom: 14 },
  footer: { paddingVertical: 14, paddingHorizontal: 20, borderTopWidth: 1, borderTopColor: "#d8e7f2", alignItems: "center", backgroundColor: "#ffffff" },
  footerText: { color: "#71899d", fontSize: 12 },
  busyIndicator: { marginBottom: 8 },
  screenSection: { paddingBottom: 14 },
  screenTitle: { color: "#183b4e", fontSize: 29, lineHeight: 36, fontWeight: "800", letterSpacing: -0.7, marginBottom: 16 },
  backLink: { minHeight: 42, flexDirection: "row", alignItems: "center", alignSelf: "flex-start", gap: 6, marginBottom: 8 },
  backLinkText: { color: "#147998", fontSize: 14, fontWeight: "700" },
  welcomeScreen: { flex: 1, justifyContent: "flex-start", paddingTop: 6, paddingBottom: 14 },
  welcomeOptionsGroup: { width: "100%" },
  welcomeLogoStage: { height: 172, alignItems: "center", justifyContent: "flex-start", overflow: "visible" },
  welcomeLogoGroup: { alignItems: "center", width: "100%" },
  welcomeLogoClip: { width: 112, height: 94, alignItems: "flex-start", overflow: "hidden" },
  welcomeLogoImage: { width: 112, height: 94 },
  welcomeTravelDot: { position: "absolute", width: 10, height: 10, borderRadius: 5, top: 34, left: "50%", marginLeft: -5, backgroundColor: "#13c4e8", borderWidth: 2, borderColor: "#ffffff" },
  welcomeWordmark: { color: "#0756ad", fontSize: 38, fontWeight: "900", letterSpacing: -1.6, lineHeight: 44 },
  welcomeLoginContent: { marginTop: 8, marginBottom: 12 },
  welcomeLoginTitle: { color: "#183b4e", fontSize: 27, lineHeight: 34, fontWeight: "800", textAlign: "center", letterSpacing: -0.6 },
  welcomeSocialWrap: { width: "100%", marginBottom: 10 },
  welcomeSocialButton: { width: "100%", minHeight: 52, borderRadius: 15, borderWidth: 1, borderColor: "#dce7ea", backgroundColor: "#ffffff", flexDirection: "row", alignItems: "center", justifyContent: "center", position: "relative", shadowColor: "#173c4c", shadowOpacity: 0.04, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  welcomeSocialText: { color: "#203f50", fontSize: 15, fontWeight: "700" },
  googleMark: { position: "absolute", left: 18, color: "#4285f4", fontSize: 20, fontWeight: "800" },
  facebookMark: { position: "absolute", left: 23, color: "#1877f2", fontSize: 23, fontWeight: "900" },
  welcomeDivider: { flexDirection: "row", alignItems: "center", gap: 13, marginTop: 1, marginBottom: 9 },
  welcomeDividerLine: { flex: 1, height: 1, backgroundColor: "#dce7ea" },
  welcomeDividerText: { color: "#78909a", fontSize: 13, fontWeight: "600" },
  welcomeEmailButton: { width: "100%", minHeight: 52, borderRadius: 15, backgroundColor: "#147998", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10 },
  welcomeEmailText: { color: "#ffffff", fontSize: 15, fontWeight: "700" },
  welcomeAccountActions: { minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: 5 },
  welcomeAccountAction: { minWidth: 104, minHeight: 44, alignItems: "center", justifyContent: "center", paddingHorizontal: 14 },
  welcomeAccountText: { color: "#147998", fontSize: 15, fontWeight: "800" },
  welcomeAccountDivider: { width: 1, height: 19, backgroundColor: "#dce7ea" },
  welcomeExploreAction: { alignSelf: "center", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 40, paddingHorizontal: 14, marginTop: 4 },
  welcomeExploreText: { color: "#147998", fontSize: 14, fontWeight: "700" },
  welcomeSocialNote: { color: "#84959c", fontSize: 11, lineHeight: 16, textAlign: "center", marginTop: 1 },
  homeScreen: { paddingBottom: 20 },
  greetingRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 20 },
  greetingCopy: { flex: 1 },
  homeGreeting: { color: "#183b4e", fontSize: 28, fontWeight: "800", letterSpacing: -0.6 },
  homeSubtitle: { color: "#66808e", fontSize: 14, marginTop: 4 },
  avatarButton: { width: 46, height: 46, borderRadius: 23, backgroundColor: "#e5f1f2", alignItems: "center", justifyContent: "center", overflow: "hidden" },
  greetingAvatar: { width: 46, height: 46, borderRadius: 23 },
  homeSearchCard: { minHeight: 58, flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: "#ffffff", borderRadius: 18, borderWidth: 1, borderColor: "#e4edef", paddingLeft: 16, paddingRight: 7, shadowColor: "#173c4c", shadowOpacity: 0.06, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 2 },
  homeSearchInput: { flex: 1, minHeight: 48, color: "#183b4e", fontSize: 15, paddingVertical: 10 },
  searchSubmit: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: "#147998" },
  homeSection: { marginTop: 29 },
  sectionHeadingRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12 },
  homeSectionTitle: { color: "#183b4e", fontSize: 19, fontWeight: "800" },
  homeSectionSubtitle: { color: "#778e98", fontSize: 12, marginTop: 4 },
  sectionAction: { minHeight: 40, flexDirection: "row", alignItems: "center", gap: 2, paddingHorizontal: 3 },
  sectionActionText: { color: "#147998", fontSize: 13, fontWeight: "700" },
  horizontalCards: { gap: 12, paddingRight: 20 },
  sectionLoader: { paddingVertical: 20 },
  wideDestinationCard: { backgroundColor: "#ffffff", borderRadius: 17, overflow: "hidden", borderWidth: 1, borderColor: "#e6eef0" },
  wideDestinationImage: { width: "100%", aspectRatio: 1.45, backgroundColor: "#e5f0f2" },
  wideCardInfo: { padding: 12 },
  inlineMeta: { flexDirection: "row", alignItems: "center", gap: 4, minWidth: 0 },
  featuredHotelCard: { backgroundColor: "#ffffff", borderRadius: 17, overflow: "hidden", borderWidth: 1, borderColor: "#e6eef0" },
  featuredHotelImage: { width: "100%", height: 148, borderRadius: 0, marginBottom: 0 },
  ratingCompact: { color: "#466777", fontSize: 13, fontWeight: "700" },
  hotelCardPrice: { color: "#147998", fontSize: 14, fontWeight: "800", marginTop: 8 },
  featuredHotelEmpty: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 10, padding: 14 },
  emptyCopy: { flex: 1, minWidth: 150 },
  homeTripList: { gap: 9 },
  homeTripCard: { minHeight: 72, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 13, paddingVertical: 11, backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e6eef0", borderRadius: 16 },
  tripIconWrap: { width: 42, height: 42, alignItems: "center", justifyContent: "center", borderRadius: 14, backgroundColor: "#e9f4f4" },
  homeTripCopy: { flex: 1, minWidth: 0 },
  emptyCard: { alignItems: "center", justifyContent: "center", gap: 8, padding: 22, backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e6eef0", borderRadius: 18, marginTop: 8 },
  exploreSearchRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  exploreSearchBox: { flex: 1, minHeight: 50, flexDirection: "row", alignItems: "center", gap: 9, paddingHorizontal: 14, backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e0eaed", borderRadius: 15 },
  exploreSearchInput: { flex: 1, minHeight: 46, color: "#183b4e", fontSize: 15, paddingVertical: 9 },
  filterButton: { width: 50, height: 50, borderRadius: 15, alignItems: "center", justifyContent: "center", backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e0eaed" },
  filterButtonActive: { backgroundColor: "#e8f4f5", borderColor: "#b5d9dd" },
  filterPanel: { marginTop: 12, padding: 13, backgroundColor: "#ffffff", borderRadius: 16, borderWidth: 1, borderColor: "#e6eef0" },
  filterLabel: { color: "#456574", fontSize: 12, fontWeight: "700", marginTop: 4, marginBottom: 6 },
  filterChoices: { gap: 7, paddingBottom: 8 },
  filterChip: { minHeight: 34, justifyContent: "center", paddingHorizontal: 12, borderRadius: 17, backgroundColor: "#f1f6f7" },
  filterChipActive: { backgroundColor: "#147998" },
  filterChipText: { color: "#486574", fontSize: 12, fontWeight: "600", textTransform: "capitalize" },
  filterChipTextActive: { color: "#ffffff" },
  resultsCount: { color: "#6b838e", fontSize: 12, fontWeight: "600", marginTop: 14 },
  destinationCardWrap: { position: "relative" },
  favoriteRemove: { position: "absolute", top: 10, right: 10, width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 20, backgroundColor: "#ffffff", elevation: 2 },
  tripList: { gap: 10, marginTop: 8 },
  tripListCard: { minHeight: 84, flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e6eef0", borderRadius: 17, padding: 13 },
  tripListCopy: { flex: 1, minWidth: 0 },
  destinationTripPicker: { marginTop: 22 },
  profileCard: { alignItems: "center", padding: 22, backgroundColor: "#ffffff", borderRadius: 20, borderWidth: 1, borderColor: "#e6eef0" },
  profileAvatarWrap: { position: "relative", width: 104, height: 104, borderRadius: 52, alignItems: "center", justifyContent: "center", backgroundColor: "#e7f1f2", marginBottom: 14, overflow: "visible" },
  profileAvatar: { width: 104, height: 104, borderRadius: 52 },
  profileCamera: { position: "absolute", right: -2, bottom: 1, width: 34, height: 34, alignItems: "center", justifyContent: "center", borderRadius: 17, backgroundColor: "#147998", borderWidth: 3, borderColor: "#ffffff" },
  profileName: { color: "#183b4e", fontSize: 20, fontWeight: "800" },
  profileEmail: { color: "#718791", fontSize: 14, marginTop: 4 },
  profilePhotoAction: { minHeight: 42, flexDirection: "row", alignItems: "center", gap: 7, marginTop: 12, paddingHorizontal: 12 },
  profilePhotoActionText: { color: "#147998", fontSize: 14, fontWeight: "700" },
  removePhotoAction: { minHeight: 38, flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 12 },
  removePhotoText: { color: "#8a5260", fontSize: 13, fontWeight: "600" },
  profileSettings: { marginTop: 16, paddingHorizontal: 14, backgroundColor: "#ffffff", borderRadius: 18, borderWidth: 1, borderColor: "#e6eef0" },
  profileSettingRow: { minHeight: 76, flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: "#edf2f3" },
  profileSettingIcon: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 13, backgroundColor: "#e9f4f4" },
  profileSettingCopy: { flex: 1 },
  bottomTabs: { minHeight: 64, flexDirection: "row", alignItems: "center", justifyContent: "space-around", backgroundColor: "#ffffff", borderTopWidth: 1, borderTopColor: "#e6edef", paddingTop: 5, paddingBottom: 4, paddingHorizontal: 5, elevation: 10, shadowColor: "#163a4a", shadowOpacity: 0.07, shadowRadius: 8, shadowOffset: { width: 0, height: -3 } },
  tabButton: { flex: 1, minHeight: 56, alignItems: "center", justifyContent: "center", gap: 1 },
  tabIconWrap: { minWidth: 54, height: 30, alignItems: "center", justifyContent: "center", borderRadius: 15 },
  tabIconWrapActive: { backgroundColor: "#e5f2f2" },
  tabLabel: { color: "#778891", fontSize: 10, fontWeight: "600" },
  tabLabelActive: { color: "#116f8e", fontWeight: "800" },
  notificationButton: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 20, backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e6eef0" },
  ratingRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 7 },
  ratingTextInline: { color: "#0877a7", fontSize: 14, fontWeight: "700" },
});

export default App;
