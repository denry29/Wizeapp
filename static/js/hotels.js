/* StayingAPI hotel search, live review display, and trip-plan actions. */
(function () {
  "use strict";

  var form = document.getElementById("hotel-search-form");
  if (!form) return;

  var results = document.getElementById("hotel-results");
  var status = document.getElementById("hotel-search-status");
  var tripOptions = JSON.parse(
    document.getElementById("trip-options").dataset.trips);
  var today = new Date();
  today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
  var tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  var afterTomorrow = new Date(tomorrow);
  afterTomorrow.setDate(afterTomorrow.getDate() + 1);
  form.elements.check_in.min = tomorrow.toISOString().slice(0, 10);
  form.elements.check_out.min = afterTomorrow.toISOString().slice(0, 10);
  form.elements.check_in.value = tomorrow.toISOString().slice(0, 10);
  form.elements.check_out.value = afterTomorrow.toISOString().slice(0, 10);
  form.elements.check_in.addEventListener("change", function () {
    var minCheckout = new Date(form.elements.check_in.value + "T00:00:00");
    minCheckout.setDate(minCheckout.getDate() + 1);
    form.elements.check_out.min = minCheckout.toISOString().slice(0, 10);
    if (form.elements.check_out.value < form.elements.check_out.min) {
      form.elements.check_out.value = form.elements.check_out.min;
    }
  });

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function hasValue(value) {
    return value !== null && value !== undefined && value !== "";
  }

  function jsonText(value) {
    if (typeof value === "string" || typeof value === "number"
        || typeof value === "boolean") return String(value);
    return JSON.stringify(value);
  }

  function safeUrl(value) {
    if (typeof value !== "string") return null;
    try {
      var url = new URL(value);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
    } catch (error) {
      return null;
    }
  }

  function money(amount, currency) {
    if (!hasValue(amount) || !hasValue(currency)) return null;
    var number = Number(amount);
    if (!Number.isFinite(number)) return null;
    return number.toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    }) + " " + currency;
  }

  function addDetail(parent, label, value) {
    if (!hasValue(value)) return;
    var line = element("p", "small");
    line.appendChild(element("strong", "", label + ": "));
    line.appendChild(document.createTextNode(jsonText(value)));
    parent.appendChild(line);
  }

  function propertyLocation(hotel) {
    var location = hotel.location || {};
    return [location.city, location.country, location.address]
      .filter(hasValue).join(", ");
  }

  function buildGallery(hotel) {
    var gallery = element("div", "hotel-gallery");
    var images = Array.isArray(hotel.images) ? hotel.images : [];
    var current = 0;
    var placeholder = element("div", "hotel-placeholder", "Photo unavailable");
    var image = element("img", "hotel-image");
    image.alt = hotel.name + " property photo";
    image.hidden = true;
    image.addEventListener("error", function () {
      image.hidden = true;
      placeholder.hidden = false;
    });
    image.addEventListener("load", function () {
      image.hidden = false;
      placeholder.hidden = true;
    });

    function showImage(index) {
      current = (index + images.length) % images.length;
      var url = safeUrl(images[current]);
      if (!url) {
        image.removeAttribute("src");
        image.hidden = true;
        placeholder.hidden = false;
        return;
      }
      image.src = url;
    }

    gallery.appendChild(placeholder);
    gallery.appendChild(image);
    if (images.length > 1) {
      var controls = element("div", "hotel-gallery-controls");
      var previous = element("button", "btn btn-ghost btn-sm", "Previous photo");
      var next = element("button", "btn btn-ghost btn-sm", "Next photo");
      previous.type = next.type = "button";
      previous.addEventListener("click", function () { showImage(current - 1); });
      next.addEventListener("click", function () { showImage(current + 1); });
      controls.append(previous, next);
      gallery.appendChild(controls);
    }
    if (images.length) showImage(0);
    return gallery;
  }

  function tripSelector(hotel) {
    var details = element("details", "hotel-add-details");
    details.appendChild(element("summary", "", "Add to a trip"));
    var select = element("select");
    select.setAttribute("aria-label", "Choose a trip");
    select.appendChild(new Option("Choose an existing trip…", ""));
    tripOptions.forEach(function (trip) {
      var option = new Option(trip.trip_name, String(trip.trip_id));
      option.dataset.start = trip.start_date;
      option.dataset.end = trip.end_date;
      select.appendChild(option);
    });
    select.appendChild(new Option("Create a new trip…", "__new__"));
    details.appendChild(select);

    var newTrip = element("div", "hotel-new-trip");
    newTrip.hidden = true;
    var nameLabel = element("label", "", "New trip name");
    var nameInput = element("input");
    nameInput.type = "text";
    nameInput.maxLength = 100;
    nameInput.value = "Trip to " + ((hotel.location || {}).city || "Asia");
    nameLabel.appendChild(nameInput);
    var dateRow = element("div", "field-row");
    var startLabel = element("label", "", "Trip start");
    var startInput = element("input");
    startInput.type = "date";
    startInput.value = hotel.dates.check_in;
    startLabel.appendChild(startInput);
    var endLabel = element("label", "", "Trip end");
    var endInput = element("input");
    endInput.type = "date";
    endInput.value = hotel.dates.check_out;
    endLabel.appendChild(endInput);
    dateRow.append(startLabel, endLabel);
    newTrip.append(nameLabel, dateRow);
    details.appendChild(newTrip);

    var feedback = element("p", "hint");
    feedback.setAttribute("aria-live", "polite");
    var save = element("button", "btn btn-primary btn-sm", "Add hotel");
    save.type = "button";
    details.append(feedback, save);
    select.addEventListener("change", function () {
      newTrip.hidden = select.value !== "__new__";
      feedback.textContent = "";
    });

    save.addEventListener("click", async function () {
      feedback.textContent = "Saving hotel to your trip…";
      save.disabled = true;
      try {
        var tripId = select.value;
        if (tripId === "__new__") {
          if (nameInput.value.trim().length < 2
              || startInput.value > hotel.dates.check_in
              || endInput.value < hotel.dates.check_out
              || endInput.value < startInput.value) {
            throw new Error("The new trip dates must include this hotel stay.");
          }
          var created = await window.Wize.request("/api/trips", {
            method: "POST",
            body: {
              trip_name: nameInput.value.trim(),
              start_date: startInput.value,
              end_date: endInput.value,
              status: "planning",
              description: "Hotel stay in " + ((hotel.location || {}).city || "Asia")
            }
          });
          if (!created.ok) throw new Error(
            (created.data && created.data.error) || "Could not create the trip.");
          tripId = String(created.data.trip.trip_id);
        } else if (!tripId) {
          throw new Error("Choose an existing trip or create a new one.");
        } else {
          var selected = select.options[select.selectedIndex];
          if (selected.dataset.start > hotel.dates.check_in
              || selected.dataset.end < hotel.dates.check_out) {
            throw new Error("This trip's dates do not include the hotel stay.");
          }
        }

        var saved = await window.Wize.request(
          "/api/trips/" + encodeURIComponent(tripId) + "/saved-options",
          {
            method: "POST",
            body: {
              option_type: "hotel",
              title: hotel.name,
              amount: hasValue(hotel.total_price) ? hotel.total_price : null,
              currency: hasValue(hotel.total_price) ? hotel.currency : null,
              details: {
                hotel_id: hotel.hotel_id,
                platform_listing_id: hotel.platform_listing_id,
                location: hotel.location,
                images: hotel.images,
                image_url: hotel.image_url,
                description: hotel.description,
                property_type: hotel.property_type,
                star_rating: hotel.star_rating,
                rating: hotel.rating,
                rating_scale: hotel.rating_scale,
                review_count: hotel.review_count,
                review_summary: hotel.review_summary,
                max_occupancy: hotel.max_occupancy,
                bedrooms: hotel.bedrooms,
                bathrooms: hotel.bathrooms,
                host: hotel.host,
                amenities: hotel.amenities,
                room_type: hotel.room_type,
                bed_type: hotel.bed_type,
                availability: hotel.availability,
                booking_url: hotel.booking_url,
                price_source: hotel.price_source,
                price_per_night: hotel.price_per_night,
                total_price: hotel.total_price,
                taxes: hotel.taxes,
                fees: hotel.fees,
                currency: hotel.currency,
                nights: hotel.nights,
                rooms: hotel.rooms,
                dates: hotel.dates,
                cancellation_policy: hotel.cancellation_policy,
                provider: hotel.provider
              }
            }
          }
        );
        if (!saved.ok) throw new Error(
          (saved.data && saved.data.error) || "Could not save this hotel.");
        feedback.textContent = "Hotel added to " + saved.data.option.title + ".";
        select.value = tripId;
        newTrip.hidden = true;
      } catch (error) {
        feedback.textContent = error.message || "Could not save this hotel.";
      } finally {
        save.disabled = false;
      }
    });
    return details;
  }

  function renderReviews(container, hotel) {
    if (!hotel.platform || !hotel.platform_listing_id) return;
    var button = element("button", "btn btn-ghost btn-sm", "View reviews");
    button.type = "button";
    var panel = element("div", "hotel-reviews");
    panel.hidden = true;
    button.addEventListener("click", async function () {
      panel.hidden = false;
      panel.replaceChildren(element("p", "muted small", "Loading reviews…"));
      button.disabled = true;
      try {
        var query = new URLSearchParams({
          platform: hotel.provider,
          listing_id: hotel.platform_listing_id
        });
        var response = await fetch("/api/hotels/reviews?" + query.toString(), {
          credentials: "same-origin",
          headers: { "Accept": "application/json" }
        });
        var payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Reviews are unavailable.");
        panel.replaceChildren();
        if (!payload.reviews.length) {
          panel.appendChild(element("p", "muted small",
            "No detailed reviews were returned by the provider."));
        }
        payload.reviews.forEach(function (review) {
          if (!review || typeof review !== "object") return;
          var entry = element("article", "hotel-review");
          var reviewRating = hasValue(review.rating) ? review.rating : null;
          if (hasValue(reviewRating) && hasValue(review.ratingScale)) {
            reviewRating += " / " + review.ratingScale;
          }
          addDetail(entry, "Rating", reviewRating);
          addDetail(entry, "Date", review.date || review.createdAt);
          addDetail(entry, "Title", review.title);
          addDetail(entry, "Author", review.author);
          var text = review.text || review.content || review.comment;
          addDetail(entry, "Review", text);
          addDetail(entry, "Owner response", review.ownerResponse);
          if (entry.childNodes.length) panel.appendChild(entry);
        });
      } catch (error) {
        panel.replaceChildren(element("p", "field-error",
          error.message || "Reviews are unavailable."));
      } finally {
        button.disabled = false;
      }
    });
    container.append(button, panel);
  }

  function renderHotel(hotel) {
    var card = element("article", "hotel-card");
    card.appendChild(buildGallery(hotel));
    var content = element("div", "hotel-content");
    content.appendChild(element("h2", "", hotel.name));
    var location = propertyLocation(hotel);
    if (location) content.appendChild(element("p", "muted", location));

    if (hasValue(hotel.star_rating)) {
      content.appendChild(element("p", "small",
        "Star rating: " + hotel.star_rating));
    }
    if (hasValue(hotel.rating)) {
      var ratingText = "Guest rating: " + hotel.rating;
      if (hasValue(hotel.rating_scale)) ratingText += " / " + hotel.rating_scale;
      if (hasValue(hotel.review_count)) {
        ratingText += " · " + hotel.review_count + " review"
          + (Number(hotel.review_count) === 1 ? "" : "s");
      }
      content.appendChild(element("p", "hotel-rating", ratingText));
    } else if (hasValue(hotel.review_count)) {
      content.appendChild(element("p", "muted small",
        hotel.review_count + " reviews"));
    }
    if (hotel.description) content.appendChild(element("p", "", hotel.description));

    var price = element("div", "hotel-price");
    var nightly = money(hotel.price_per_night, hotel.currency);
    var total = money(hotel.total_price, hotel.currency);
    if (nightly) price.appendChild(element("p", "money", nightly + " / night"));
    if (hotel.nights) {
      price.appendChild(element("p", "muted small",
        hotel.nights + " night" + (hotel.nights === 1 ? "" : "s")
          + " · " + hotel.rooms + " room" + (hotel.rooms === 1 ? "" : "s")));
    }
    if (total) {
      price.appendChild(element("p", "hotel-total", "Total stay: " + total));
    } else {
      price.appendChild(element("p", "muted small",
        "Total price was not provided for these dates."));
    }
    addDetail(price, "Taxes", hotel.taxes);
    addDetail(price, "Fees", hotel.fees);
    content.appendChild(price);

    var more = element("details", "hotel-more");
    more.appendChild(element("summary", "", "More property information"));
    addDetail(more, "Property type", hotel.property_type);
    addDetail(more, "Maximum occupancy", hotel.max_occupancy);
    addDetail(more, "Bedrooms", hotel.bedrooms);
    addDetail(more, "Bathrooms", hotel.bathrooms);
    addDetail(more, "Host", hotel.host);
    addDetail(more, "Room", hotel.room_type);
    addDetail(more, "Bed type", hotel.bed_type);
    addDetail(more, "Availability", hotel.availability);
    addDetail(more, "Cancellation", hotel.cancellation_policy);
    addDetail(more, "Amenities", hotel.amenities);
    addDetail(more, "Review summary", hotel.review_summary);
    if (hotel.provider) addDetail(more, "Provider", hotel.provider);
    addDetail(more, "Price source", hotel.price_source);
    var bookingUrl = safeUrl(hotel.booking_url);
    if (bookingUrl) {
      var bookingLink = element("a", "btn btn-ghost btn-sm", "View provider");
      bookingLink.href = bookingUrl;
      bookingLink.target = "_blank";
      bookingLink.rel = "noopener noreferrer";
      more.appendChild(bookingLink);
    }
    content.appendChild(more);
    renderReviews(content, hotel);
    content.appendChild(tripSelector(hotel));
    card.appendChild(content);
    return card;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    status.hidden = false;
    status.className = "flash";
    status.textContent = "Searching live hotel availability…";
    results.replaceChildren();
    var submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      var query = new URLSearchParams(new FormData(form));
      query.delete("csrf_token");
      var response = await fetch("/api/hotels/search?" + query.toString(), {
        credentials: "same-origin",
        headers: { "Accept": "application/json" }
      });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Hotel search failed.");
      if (!payload.hotels.length) {
        status.textContent = "No hotel results were returned for those dates.";
        return;
      }
      status.hidden = true;
      payload.hotels.forEach(function (hotel) {
        results.appendChild(renderHotel(hotel));
      });
    } catch (error) {
      status.className = "flash flash-error";
      status.textContent = error.message || "Hotel search failed.";
    } finally {
      submit.disabled = false;
    }
  });
})();
